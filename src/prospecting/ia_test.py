"""
Module IA_TEST — Multi-IA test runner
POST /api/ia-test/run

- Appelle OpenAI, Anthropic, Gemini (si clés présentes)
- temperature ≤ 0.2
- Extraction entités robuste (nom + domaine)
- Matching flou normalisé
- Log erreurs sans stopper
- Stocke TestRun pour chaque modèle × prospect
"""
import json
import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .database import db_create_run, db_list_runs, db_save_prospect, jdumps, jloads
from .models import ProspectDB, ProspectStatus, TestRunDB
from .prospect_scan import get_queries

logger = logging.getLogger(__name__)

TEMPERATURE = 0.1  # ≤ 0.2

# Suffixes légaux à ignorer dans le matching
_LEGAL = re.compile(
    r"\b(sarl|sas|eurl|srl|snc|sa|spa|ltd|llc|gmbh|inc|cie|co|groupe|group|et fils|et associés|&)\b",
    re.IGNORECASE,
)

# ─────────────────────────── NORMALISATION ───────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_name(name: str) -> str:
    """Normalise un nom d'entreprise pour le matching."""
    if not name:
        return ""
    name = name.lower()
    name = _strip_accents(name)
    name = _LEGAL.sub(" ", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    return " ".join(name.split())


def extract_domain(url: str) -> str:
    """Extrait le nom de domaine sans TLD ni www."""
    if not url:
        return ""
    url = re.sub(r"^https?://", "", url.lower())
    url = re.sub(r"^www\.", "", url)
    domain = url.split("/")[0].split("?")[0]
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else domain


# ─────────────────────────── MATCHING FLOU ───────────────────────────

def is_mentioned(
    text: str,
    prospect_name: str,
    website: Optional[str] = None,
    threshold: float = 0.82,
) -> bool:
    """
    True si le prospect est mentionné dans text.
    1. Substring exact normalisé
    2. Tous les mots significatifs présents
    3. SequenceMatcher sur fenêtre glissante
    4. Domain match
    """
    norm_text = normalize_name(text)
    norm_name = normalize_name(prospect_name)
    if not norm_name:
        return False

    # 1. Substring
    if norm_name in norm_text:
        return True

    # 2. Tous les mots significatifs (len > 2)
    sig_words = [w for w in norm_name.split() if len(w) > 2]
    if sig_words and all(w in norm_text for w in sig_words):
        return True

    # 3. Fenêtre glissante SequenceMatcher
    name_tokens = norm_name.split()
    text_tokens = norm_text.split()
    window = max(len(name_tokens) + 3, 5)
    for i in range(len(text_tokens)):
        chunk = " ".join(text_tokens[i : i + window])
        if SequenceMatcher(None, norm_name, chunk).ratio() >= threshold:
            return True

    # 4. Domain match
    if website:
        domain = extract_domain(website)
        if domain and len(domain) > 2 and domain in norm_text:
            return True

    return False


# ─────────────────────────── EXTRACTION ENTITÉS ───────────────────────────

def extract_entities(text: str) -> List[Dict]:
    """
    Extrait URLs et noms d'entreprises potentiels d'une réponse IA.
    """
    entities: List[Dict] = []

    # URLs
    for url in re.findall(r"https?://\S+", text):
        domain = extract_domain(url)
        if domain:
            entities.append({"type": "url", "value": url, "domain": domain})

    # Noms propres : 1-4 mots commençant par majuscule
    for match in re.finditer(
        r"(?:[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝ][a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüý]+\s?){1,4}",
        text,
    ):
        name = match.group().strip()
        if len(name) > 3:
            entities.append({"type": "company", "value": name})

    # Dédupliquer
    seen: set = set()
    unique: List[Dict] = []
    for e in entities:
        key = e["value"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def extract_competitors(entities: List[Dict], target_name: str, target_website: Optional[str]) -> List[str]:
    """Retourne les entités qui ne sont PAS le prospect cible."""
    norm_target = normalize_name(target_name)
    target_domain = extract_domain(target_website or "")
    competitors: List[str] = []
    for e in entities:
        val = e["value"]
        norm_val = normalize_name(val)
        # Exclure le prospect lui-même
        if norm_target and norm_target in norm_val:
            continue
        if target_domain and target_domain in val.lower():
            continue
        competitors.append(val)
    return competitors


# ─────────────────────────── ADAPTATEURS IA ───────────────────────────

def _call_openai(query: str) -> str:
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": query}],
        temperature=TEMPERATURE,
        max_tokens=800,
    )
    return resp.choices[0].message.content or ""


def _call_anthropic(query: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": query}],
    )
    return resp.content[0].text if resp.content else ""


def _call_gemini(query: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={"temperature": TEMPERATURE, "max_output_tokens": 800},
    )
    resp = model.generate_content(query)
    return resp.text or ""


AI_CALLERS = {
    "openai":    (_call_openai,    "OPENAI_API_KEY"),
    "anthropic": (_call_anthropic, "ANTHROPIC_API_KEY"),
    "gemini":    (_call_gemini,    "GEMINI_API_KEY"),
}


def get_active_models() -> List[str]:
    """Retourne les modèles dont la clé est configurée."""
    return [m for m, (_, key) in AI_CALLERS.items() if os.getenv(key)]


# ─────────────────────────── RUN PRINCIPAL ───────────────────────────

def run_ia_test_for_prospect(
    db: Session,
    prospect: ProspectDB,
    dry_run: bool = False,
) -> List[TestRunDB]:
    """
    Exécute 1 run (= 3 modèles × 5 requêtes) pour un prospect.
    dry_run=True : génère les structures mais n'appelle pas les APIs.
    Retourne la liste des TestRunDB créés.
    """
    queries = get_queries(prospect.profession, prospect.city)
    models = get_active_models() if not dry_run else list(AI_CALLERS.keys())

    if not models:
        logger.warning("Aucun modèle IA configuré (vérifier les clés API)")
        return []

    # Passer TESTING
    if prospect.status == ProspectStatus.SCHEDULED.value:
        prospect.status = ProspectStatus.TESTING.value
        db.commit()

    created_runs: List[TestRunDB] = []

    for model_name in models:
        caller, key_name = AI_CALLERS[model_name]
        raw_answers: List[str] = []
        entities_per_query: List[List[Dict]] = []
        mention_per_query: List[bool] = []
        all_competitors: List[str] = []
        notes_parts: List[str] = []
        mentioned_in_any = False

        for qi, query in enumerate(queries):
            if dry_run:
                answer = f"[DRY_RUN] Réponse simulée pour : {query}"
            else:
                try:
                    answer = caller(query)
                except Exception as exc:
                    logger.error(f"[{model_name}] Q{qi+1} erreur: {exc}")
                    answer = f"[ERREUR] {exc}"
                    notes_parts.append(f"Q{qi+1} erreur {model_name}: {exc}")

            raw_answers.append(answer)
            entities = extract_entities(answer)
            entities_per_query.append(entities)

            mentioned = is_mentioned(answer, prospect.name, prospect.website)
            mention_per_query.append(mentioned)
            if mentioned:
                mentioned_in_any = True

            competitors = extract_competitors(entities, prospect.name, prospect.website)
            all_competitors.extend(competitors)

        # Dédupliquer concurrents
        seen: set = set()
        unique_competitors = [c for c in all_competitors if not (c.lower() in seen or seen.add(c.lower()))]

        run = TestRunDB(
            run_id=str(uuid.uuid4()),
            campaign_id=prospect.campaign_id,
            prospect_id=prospect.prospect_id,
            ts=datetime.utcnow(),
            model=model_name,
            queries=jdumps(queries),
            raw_answers=jdumps(raw_answers),
            extracted_entities=jdumps([
                [{"type": e["type"], "value": e["value"]} for e in eq]
                for eq in entities_per_query
            ]),
            mentioned_target=mentioned_in_any,
            mention_per_query=jdumps(mention_per_query),
            competitors_entities=jdumps(unique_competitors[:20]),  # top 20
            notes="; ".join(notes_parts) if notes_parts else None,
        )
        db_create_run(db, run)
        created_runs.append(run)

    # Passer TESTED
    if prospect.status == ProspectStatus.TESTING.value:
        prospect.status = ProspectStatus.TESTED.value
        db.commit()

    return created_runs


def run_ia_test_campaign(
    db: Session,
    campaign_id: str,
    prospect_ids: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict:
    """Lance les tests pour tous les prospects SCHEDULED d'une campagne."""
    from .database import db_list_prospects, db_get_prospect

    if prospect_ids:
        prospects = [p for pid in prospect_ids if (p := db_get_prospect(db, pid))]
    else:
        prospects = db_list_prospects(db, campaign_id, status=ProspectStatus.SCHEDULED.value)

    results = {"total": len(prospects), "processed": 0, "runs_created": 0, "errors": []}

    for prospect in prospects:
        try:
            runs = run_ia_test_for_prospect(db, prospect, dry_run=dry_run)
            results["processed"] += 1
            results["runs_created"] += len(runs)
        except Exception as exc:
            logger.error(f"Prospect {prospect.prospect_id} erreur: {exc}")
            results["errors"].append({"prospect_id": prospect.prospect_id, "error": str(exc)})

    return results
