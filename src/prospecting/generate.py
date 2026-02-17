"""
Module GENERATE — Livrables

- audit_generate   : HTML export (score, concurrents, synthèse, BONUS plan d'action)
- landing_generate : template /couvreur?t={token}
- email_generate   : subject + body avec variables
- delivery         : SendQueue CSV + fichiers emails — AUCUN ENVOI AUTO
"""
import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .database import db_list_runs, jloads
from .models import ProspectDB, ProspectStatus

SEND_QUEUE_DIR = Path(__file__).parent.parent.parent / "send_queue"
SEND_QUEUE_DIR.mkdir(exist_ok=True)

SIGNATURE = os.getenv("SENDER_SIGNATURE", "L'équipe EURKAI")
BASE_URL   = os.getenv("BASE_URL", "http://localhost:8000")


# ─────────────────────────── HELPERS ───────────────────────────

def _get_competitors(prospect: ProspectDB, max_n: int = 2) -> List[str]:
    try:
        comps = json.loads(prospect.competitors_cited or "[]")
        return [c.title() for c in comps[:max_n]]
    except Exception:
        return []


def _runs_summary(db: Session, prospect: ProspectDB) -> Dict:
    """Résumé des runs pour un prospect."""
    runs = db_list_runs(db, prospect.prospect_id)
    total_runs    = len(runs)
    models_used   = list({r.model for r in runs})
    mentioned_any = any(r.mentioned_target for r in runs)
    mention_counts = sum(1 for r in runs if r.mentioned_target)
    run_dates     = sorted({r.ts.strftime("%d/%m/%Y") for r in runs}) if runs else []

    # mention par requête (agrégé sur tous les runs)
    query_mentions = [0] * 5
    query_labels   = [""] * 5
    for r in runs:
        mlist  = jloads(r.mention_per_query)
        qlist  = jloads(r.queries)
        for qi in range(min(5, len(mlist))):
            if mlist[qi]:
                query_mentions[qi] += 1
            if not query_labels[qi] and qi < len(qlist):
                query_labels[qi] = qlist[qi]

    return {
        "total_runs":    total_runs,
        "models":        models_used,
        "dates":         run_dates,
        "mentioned_any": mentioned_any,
        "mention_count": mention_counts,
        "query_labels":  query_labels,
        "query_mentions":query_mentions,
    }


# ─────────────────────────── AUDIT HTML ───────────────────────────

_AUDIT_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Audit IA — {company_name}</title>
<style>
  body{{font-family:Arial,sans-serif;margin:0;padding:40px;color:#222;max-width:900px;margin:auto}}
  h1{{color:#1a1a2e;border-bottom:3px solid #e94560;padding-bottom:10px}}
  h2{{color:#16213e;margin-top:40px}}
  .score-box{{background:#f0f4ff;border-left:5px solid #e94560;padding:20px 30px;margin:20px 0;border-radius:4px}}
  .score-number{{font-size:56px;font-weight:bold;color:#e94560}}
  table{{border-collapse:collapse;width:100%;margin:16px 0}}
  th{{background:#16213e;color:#fff;padding:10px 14px;text-align:left}}
  td{{padding:9px 14px;border-bottom:1px solid #e8e8e8}}
  tr:nth-child(even){{background:#f9f9fb}}
  .badge-ok{{background:#2ecc71;color:#fff;padding:3px 10px;border-radius:12px;font-size:12px}}
  .badge-no{{background:#e74c3c;color:#fff;padding:3px 10px;border-radius:12px;font-size:12px}}
  .plan-action{{background:#fffbea;border:1px solid #f1c40f;padding:20px 30px;border-radius:6px;margin-top:30px}}
  .plan-action h2{{color:#b8860b;margin-top:0}}
  .checklist li{{margin:8px 0}}
  .checklist li::before{{content:"☑ ";color:#2ecc71}}
  footer{{margin-top:60px;color:#888;font-size:12px;border-top:1px solid #ddd;padding-top:20px}}
</style>
</head>
<body>
<h1>🤖 Audit IA — Visibilité dans les réponses des intelligences artificielles</h1>
<p><strong>Entreprise :</strong> {company_name}<br>
<strong>Ville :</strong> {city}<br>
<strong>Secteur :</strong> {profession}<br>
<strong>Date du rapport :</strong> {report_date}</p>

<div class="score-box">
  <div>Score de visibilité IA</div>
  <div class="score-number">{score}/10</div>
  <div>{justification_short}</div>
</div>

<h2>📊 Résultats des tests</h2>
<p>Tests réalisés : <strong>{total_runs} runs</strong> sur {models_str} | Dates : {dates_str}</p>

<table>
  <tr><th>Requête</th><th>Cité</th></tr>
  {query_rows}
</table>

<h2>🏆 Concurrents identifiés</h2>
<p>Les entreprises citées régulièrement par les IA :</p>
<ul>
  {competitor_items}
</ul>

<h2>📋 Synthèse</h2>
<p>{synthesis}</p>

<div class="plan-action">
<h2>✅ BONUS — Plan d'action prioritaire</h2>
<p>Pour améliorer votre visibilité IA dans les 90 prochains jours :</p>
<ul class="checklist">
  <li><strong>Google Business Profile</strong> — Compléter à 100% (description, catégories, photos, horaires)</li>
  <li><strong>Avis Google</strong> — Viser 40+ avis avec réponses systématiques (les IA lisent les avis)</li>
  <li><strong>Contenu FAQ</strong> — Publier 5-10 pages répondant aux questions exactes testées ci-dessus</li>
  <li><strong>Citations locales</strong> — Inscription sur PagesJaunes, Yelp, Houzz, Habitissimo</li>
  <li><strong>Structured Data</strong> — Ajouter JSON-LD LocalBusiness + AggregateRating sur votre site</li>
  <li><strong>Mentions presse</strong> — 1 article de blog local ou interview = signal fort pour les LLMs</li>
  <li><strong>Cohérence NAP</strong> — Nom / Adresse / Téléphone identiques partout (critère algorithmes IA)</li>
  <li><strong>Site optimisé</strong> — Titre H1 incluant ville + profession (ex : « Couvreur à {city} »)</li>
</ul>
<p><em>Délai estimé pour apparaître dans les réponses IA : 2-4 mois selon l'action menée.</em></p>
</div>

<footer>
Rapport généré le {report_date} — Tests réalisés sur {models_str}.<br>
Les réponses IA peuvent varier ; résultats basés sur tests répétés horodatés.<br>
© EURKAI — <a href="{base_url}">ai-seo-audit</a>
</footer>
</body>
</html>
"""

def audit_generate(db: Session, prospect: ProspectDB) -> str:
    """Génère le HTML d'audit. Retourne le contenu HTML."""
    summary     = _runs_summary(db, prospect)
    competitors = _get_competitors(prospect, 5)
    score       = prospect.ia_visibility_score or 0
    justif      = (prospect.score_justification or "").split("\n")[0]

    query_rows = ""
    for qi, (label, count) in enumerate(zip(summary["query_labels"], summary["query_mentions"])):
        cited   = count > 0
        badge   = f'<span class="badge-ok">Cité</span>' if cited else f'<span class="badge-no">Non cité</span>'
        q_label = label or f"Requête {qi+1}"
        query_rows += f"<tr><td>{q_label}</td><td>{badge}</td></tr>\n"

    competitor_items = "\n".join(f"<li>{c}</li>" for c in competitors) if competitors else "<li>Aucun concurrent identifié</li>"

    visibility_word = "très faible" if score < 3 else "faible" if score < 6 else "moyenne"
    synthesis = (
        f"{prospect.name} présente une visibilité IA {visibility_word} (score {score}/10). "
        f"Sur {summary['total_runs']} tests réalisés, l'entreprise est {'mentionnée dans ' + str(summary['mention_count']) + ' run(s)' if summary['mentioned_any'] else 'jamais mentionnée'}. "
        + (f"Les concurrents {', '.join(competitors[:2])} sont régulièrement cités à sa place." if competitors else "")
    )

    html = _AUDIT_TEMPLATE.format(
        company_name=prospect.name,
        city=prospect.city,
        profession=prospect.profession,
        report_date=datetime.utcnow().strftime("%d/%m/%Y"),
        score=score,
        justification_short=justif,
        total_runs=summary["total_runs"],
        models_str=", ".join(summary["models"]) or "—",
        dates_str=", ".join(summary["dates"][:3]) or "—",
        query_rows=query_rows,
        competitor_items=competitor_items,
        synthesis=synthesis,
        base_url=BASE_URL,
    )

    # Sauvegarder
    out_dir = SEND_QUEUE_DIR / prospect.prospect_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit.html").write_text(html, encoding="utf-8")
    return html


# ─────────────────────────── LANDING TOKEN ───────────────────────────

def landing_url(prospect: ProspectDB) -> str:
    return f"{BASE_URL}/couvreur?t={prospect.landing_token}"


# ─────────────────────────── EMAIL ───────────────────────────

def email_generate(db: Session, prospect: ProspectDB) -> Dict:
    """Génère subject + body email. Retourne un dict."""
    competitors = _get_competitors(prospect, 2)
    comp1 = competitors[0] if len(competitors) > 0 else "vos concurrents"
    comp2 = competitors[1] if len(competitors) > 1 else ""
    l_url = landing_url(prospect)
    video = prospect.video_url or "[VIDÉO À AJOUTER]"

    subject = f"À {prospect.city}, ChatGPT recommande {comp1}. Pas vous."

    body = f"""Bonjour,

J'ai testé ce que répondent plusieurs IA lorsqu'un client cherche un {prospect.profession} à {prospect.city}.

Sur des tests répétés, {comp1}{' (et parfois ' + comp2 + ')' if comp2 else ''} est régulièrement cité. Votre entreprise n'apparaît pas.

Vidéo (90s) : {video}
Synthèse + options : {l_url}

— {SIGNATURE}

---
Vous recevez ce message car votre entreprise a été auditée dans le cadre d'une étude de marché locale.
"""

    email_data = {
        "prospect_id":   prospect.prospect_id,
        "prospect_name": prospect.name,
        "city":          prospect.city,
        "profession":    prospect.profession,
        "subject":       subject,
        "body":          body,
        "landing_url":   l_url,
        "video_url":     video,
        "competitor_1":  comp1,
        "competitor_2":  comp2,
    }

    # Sauvegarder
    out_dir = SEND_QUEUE_DIR / prospect.prospect_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "email.json").write_text(json.dumps(email_data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "email_body.txt").write_text(f"SUBJECT: {subject}\n\n{body}", encoding="utf-8")

    return email_data


# ─────────────────────────── VIDEO SCRIPT ───────────────────────────

def video_script_generate(prospect: ProspectDB) -> str:
    """Génère le script vidéo 90s (6 phrases imposées)."""
    competitors = _get_competitors(prospect, 2)
    comp1 = competitors[0] if len(competitors) > 0 else "[concurrent principal]"
    comp2 = competitors[1] if len(competitors) > 1 else "[concurrent secondaire]"
    l_url = landing_url(prospect)

    script = f"""SCRIPT VIDÉO — {prospect.name} / {prospect.city}
Durée cible : 90 secondes

1. « Bonjour {prospect.name}, j'ai testé ce que répondent les IA quand un client cherche un {prospect.profession} à {prospect.city}. »
2. « Voici la requête — je lance le test. »
3. (silence + scroll) « Comme vous voyez, {comp1} et {comp2} sont cités. »
4. (scroll) « Votre entreprise n'apparaît pas dans ces résultats. »
5. « On a répété ces tests sur plusieurs créneaux et sur plusieurs IA : le constat est stable. »
6. « Je vous ai préparé la synthèse + le plan d'action ici : {l_url} »
"""
    out_dir = SEND_QUEUE_DIR / prospect.prospect_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "video_script.txt").write_text(script, encoding="utf-8")
    return script


# ─────────────────────────── SEND QUEUE (CSV) ───────────────────────────

def delivery_generate(db: Session, prospects: List[ProspectDB]) -> str:
    """
    Génère le CSV SendQueue + emails de tous les prospects éligibles.
    AUCUN ENVOI AUTO.
    Retourne le chemin du CSV.
    """
    csv_path = SEND_QUEUE_DIR / f"send_queue_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    rows: List[Dict] = []

    for prospect in prospects:
        if not prospect.eligibility_flag:
            continue
        email_data = email_generate(db, prospect)
        audit_generate(db, prospect)
        video_script_generate(prospect)
        rows.append({
            "prospect_id":   prospect.prospect_id,
            "name":          prospect.name,
            "city":          prospect.city,
            "profession":    prospect.profession,
            "email":         "",  # à compléter manuellement
            "phone":         prospect.phone or "",
            "website":       prospect.website or "",
            "score":         prospect.ia_visibility_score or 0,
            "competitor_1":  email_data["competitor_1"],
            "competitor_2":  email_data["competitor_2"],
            "subject":       email_data["subject"],
            "landing_url":   email_data["landing_url"],
            "video_url":     email_data["video_url"],
            "status":        prospect.status,
        })

    if rows:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    return str(csv_path)


def generate_for_campaign(
    db: Session,
    campaign_id: str,
    prospect_ids: Optional[List[str]] = None,
) -> Dict:
    """Lance la génération pour tous les READY_ASSETS éligibles."""
    from .database import db_list_prospects, db_get_prospect

    if prospect_ids:
        prospects = [p for pid in prospect_ids if (p := db_get_prospect(db, pid))]
    else:
        all_p = db_list_prospects(db, campaign_id)
        prospects = [p for p in all_p if p.status == ProspectStatus.READY_ASSETS.value and p.eligibility_flag]

    csv_path = delivery_generate(db, prospects)
    return {
        "generated": len(prospects),
        "send_queue_csv": csv_path,
        "prospect_ids": [p.prospect_id for p in prospects],
    }
