"""
Module SCORING + ELIGIBILITY
POST /api/scoring/run

Règle EMAIL_OK (robuste) :
- Sur l'ensemble des runs : target_mentions = 0
- Sur au moins 2/3 modèles  → prospect JAMAIS cité dans ce modèle
- Sur au moins 4/5 requêtes → prospect JAMAIS cité pour cette requête
- ET au moins 1 concurrent stable cité (≥ MIN_COMPETITOR_RUNS)

Score /10 :
+4 invisibilité robuste (EMAIL_OK)
+2 concurrents stables cités
+1 google_ads_active
+1 reviews_count ≥ 20
+1 website présent
+1 optionnel (non implémenté, skippé)
"""
import json
import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .database import db_list_prospects, db_list_runs, db_save_prospect, jloads
from .models import ProspectDB, ProspectStatus

logger = logging.getLogger(__name__)

MIN_COMPETITOR_RUNS = 2   # concurrent doit apparaître dans au moins N runs
MODELS_REQUIRED     = 2   # sur au moins 2/3 modèles
QUERIES_REQUIRED    = 4   # sur au moins 4/5 requêtes


# ─────────────────────────── RÈGLE EMAIL_OK ───────────────────────────

def compute_email_ok(runs) -> Tuple[bool, str]:
    """
    Évalue la règle EMAIL_OK sur la liste des TestRunDB d'un prospect.
    Retourne (eligible: bool, explication: str).
    """
    if not runs:
        return False, "Aucun run disponible"

    # Grouper par modèle
    by_model: Dict[str, List] = {}
    for r in runs:
        by_model.setdefault(r.model, []).append(r)

    # Grouper par index de requête (0-4)
    by_query: Dict[int, List[bool]] = {i: [] for i in range(5)}
    for r in runs:
        mentions = jloads(r.mention_per_query)
        for qi, mentioned in enumerate(mentions):
            if qi < 5:
                by_query[qi].append(bool(mentioned))

    # — Condition 1 : modèles invisibles
    invisible_models = []
    for model, model_runs in by_model.items():
        if all(not r.mentioned_target for r in model_runs):
            invisible_models.append(model)

    # — Condition 2 : requêtes invisibles
    invisible_queries = []
    for qi, mentions_list in by_query.items():
        if mentions_list and all(not m for m in mentions_list):
            invisible_queries.append(qi)

    # — Condition 3 : concurrents stables
    competitor_counter: Counter = Counter()
    for r in runs:
        for c in jloads(r.competitors_entities):
            if isinstance(c, str):
                competitor_counter[c.lower()] += 1

    stable_competitors = [name for name, count in competitor_counter.items() if count >= MIN_COMPETITOR_RUNS]

    # — Évaluation
    models_ok   = len(invisible_models) >= MODELS_REQUIRED
    queries_ok  = len(invisible_queries) >= QUERIES_REQUIRED
    compet_ok   = len(stable_competitors) >= 1
    email_ok    = models_ok and queries_ok and compet_ok

    justif_parts = [
        f"Modèles invisibles: {len(invisible_models)}/3 ({'✓' if models_ok else '✗'})",
        f"Requêtes invisibles: {len(invisible_queries)}/5 ({'✓' if queries_ok else '✗'})",
        f"Concurrents stables: {len(stable_competitors)} ({'✓' if compet_ok else '✗'})",
    ]
    return email_ok, " | ".join(justif_parts)


# ─────────────────────────── SCORE /10 ───────────────────────────

def compute_score(
    prospect: ProspectDB,
    runs,
    email_ok: bool,
) -> Tuple[float, str, List[str]]:
    """
    Calcule le score /10 et retourne (score, justification, stable_competitors).
    """
    score = 0.0
    parts: List[str] = []

    # +4 invisibilité robuste
    if email_ok:
        score += 4
        parts.append("+4 Invisibilité IA robuste confirmée")

    # Concurrents stables
    competitor_counter: Counter = Counter()
    for r in runs:
        for c in jloads(r.competitors_entities):
            if isinstance(c, str):
                competitor_counter[c.lower()] += 1
    stable = [name for name, cnt in competitor_counter.most_common(5) if cnt >= MIN_COMPETITOR_RUNS]

    if stable:
        score += 2
        parts.append(f"+2 Concurrents stables cités ({', '.join(stable[:2])})")

    # +1 Google Ads actif
    if prospect.google_ads_active:
        score += 1
        parts.append("+1 Google Ads actif (budget marketing existant)")

    # +1 reviews ≥ 20
    if prospect.reviews_count and prospect.reviews_count >= 20:
        score += 1
        parts.append(f"+1 {prospect.reviews_count} avis (présence locale établie)")

    # +1 website présent
    if prospect.website:
        score += 1
        parts.append("+1 Site web présent")

    justification = (
        f"Score {score}/10 — EMAIL_OK: {'OUI' if email_ok else 'NON'}\n"
        + "\n".join(parts)
    )
    return score, justification, stable


# ─────────────────────────── RUN SCORING ───────────────────────────

def run_scoring(
    db: Session,
    campaign_id: str,
    prospect_ids: Optional[List[str]] = None,
) -> Dict:
    """
    Calcule score + eligibility pour tous les prospects TESTED.
    """
    from .database import db_get_prospect

    if prospect_ids:
        prospects = [p for pid in prospect_ids if (p := db_get_prospect(db, pid))]
    else:
        prospects = db_list_prospects(db, campaign_id, status=ProspectStatus.TESTED.value)

    results = {"total": len(prospects), "scored": 0, "eligible": 0}

    for prospect in prospects:
        runs = db_list_runs(db, prospect.prospect_id)
        if not runs:
            logger.warning(f"Prospect {prospect.prospect_id} — aucun run, scoring ignoré")
            continue

        email_ok, email_justif = compute_email_ok(runs)
        score, score_justif, stable_competitors = compute_score(prospect, runs, email_ok)

        # Mettre à jour le prospect
        prospect.eligibility_flag       = email_ok
        prospect.ia_visibility_score    = score
        prospect.score_justification    = f"{email_justif}\n\n{score_justif}"
        prospect.competitors_cited      = json.dumps(stable_competitors[:5], ensure_ascii=False)
        prospect.status                 = ProspectStatus.SCORED.value
        db.commit()

        results["scored"] += 1
        if email_ok:
            results["eligible"] += 1

    return results
