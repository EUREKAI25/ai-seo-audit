"""
Routes Generate — Livrables
POST /api/generate/campaign  — génère tout pour les READY_ASSETS éligibles
POST /api/generate/prospect/{id}/audit
POST /api/generate/prospect/{id}/email
GET  /couvreur                — landing page token
POST /api/prospect/{id}/assets
POST /api/prospect/{id}/mark-ready
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ...prospecting.database import get_db, db_get_prospect, db_get_prospect_by_token, jloads
from ...prospecting.models import GenerateInput, AssetsInput
from ...prospecting.generate import (
    audit_generate, email_generate, generate_for_campaign,
    delivery_generate, video_script_generate, landing_url
)
from ...prospecting.assets import set_assets, mark_ready_to_send

router = APIRouter(tags=["Generate & Assets"])


@router.post("/api/generate/campaign")
def api_generate_campaign(data: GenerateInput, db: Session = Depends(get_db)):
    """Génère audit + email + video_script + CSV SendQueue pour la campagne."""
    from ...prospecting.database import db_get_campaign
    campaign = db_get_campaign(db, data.campaign_id)
    if not campaign:
        raise HTTPException(404, "Campagne introuvable")

    result = generate_for_campaign(db, data.campaign_id, data.prospect_ids)
    return result


@router.post("/api/generate/prospect/{prospect_id}/audit")
def api_generate_audit(prospect_id: str, db: Session = Depends(get_db)):
    """Génère le rapport HTML d'audit pour un prospect."""
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect introuvable")

    html = audit_generate(db, prospect)
    return HTMLResponse(content=html)


@router.post("/api/generate/prospect/{prospect_id}/email")
def api_generate_email(prospect_id: str, db: Session = Depends(get_db)):
    """Génère le draft email pour un prospect."""
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect introuvable")

    return email_generate(db, prospect)


@router.post("/api/generate/prospect/{prospect_id}/video-script")
def api_generate_video_script(prospect_id: str, db: Session = Depends(get_db)):
    """Génère le script vidéo 90s pour un prospect."""
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect introuvable")

    return {"script": video_script_generate(prospect)}


@router.post("/api/prospect/{prospect_id}/assets")
def api_set_assets(prospect_id: str, assets: AssetsInput, db: Session = Depends(get_db)):
    """
    Enregistre video_url + screenshot_url.
    Passe le prospect en READY_ASSETS si statut=SCORED.
    """
    try:
        prospect = set_assets(db, prospect_id, assets)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "prospect_id":    prospect.prospect_id,
        "status":         prospect.status,
        "video_url":      prospect.video_url,
        "screenshot_url": prospect.screenshot_url,
    }


@router.post("/api/prospect/{prospect_id}/mark-ready")
def api_mark_ready_to_send(prospect_id: str, db: Session = Depends(get_db)):
    """
    Marque un prospect READY_TO_SEND.
    Gate stricte : video_url + screenshot_url + eligibility_flag requis.
    """
    try:
        prospect = mark_ready_to_send(db, prospect_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "prospect_id": prospect.prospect_id,
        "status":      prospect.status,
        "landing_url": landing_url(prospect),
    }


# ─────────────────────────── LANDING PAGE ───────────────────────────

_LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Audit IA — {city}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',sans-serif;background:#0f0f1a;color:#e8e8f0;line-height:1.6}}
  .hero{{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:80px 20px;text-align:center}}
  .hero h1{{font-size:clamp(26px,4vw,44px);color:#fff;max-width:750px;margin:auto 0 20px}}
  .hero h1 span{{color:#e94560}}
  .hero p{{font-size:18px;color:#aaa;max-width:600px;margin:0 auto}}
  .container{{max-width:900px;margin:0 auto;padding:0 20px}}
  section{{padding:60px 20px}}
  h2{{font-size:28px;margin-bottom:20px;color:#fff}}
  .proof-block{{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:10px;padding:30px;margin:30px 0}}
  .screenshot{{width:100%;max-width:700px;border-radius:8px;margin:20px 0;display:block}}
  table{{border-collapse:collapse;width:100%;margin:20px 0}}
  th{{background:#16213e;color:#aaa;padding:10px 16px;font-size:13px;text-align:left;text-transform:uppercase}}
  td{{padding:12px 16px;border-bottom:1px solid #2a2a4e;color:#ddd}}
  .cited{{color:#e94560;font-weight:bold}}
  .not-cited{{color:#2ecc71}}
  .plans{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px;margin:40px 0}}
  .plan{{background:#1a1a2e;border:1px solid #2a2a4e;border-radius:12px;padding:30px;position:relative}}
  .plan.best{{border-color:#e94560;background:#1e0a12}}
  .plan .badge{{position:absolute;top:-12px;right:20px;background:#e94560;color:#fff;padding:4px 12px;border-radius:20px;font-size:12px}}
  .plan h3{{font-size:22px;color:#fff;margin-bottom:10px}}
  .plan .price{{font-size:40px;font-weight:bold;color:#e94560;margin:10px 0}}
  .plan .price span{{font-size:16px;color:#aaa}}
  .plan ul{{list-style:none;padding:0;margin:20px 0}}
  .plan ul li{{padding:6px 0;color:#ccc;border-bottom:1px solid #2a2a4e}}
  .plan ul li::before{{content:"✓ ";color:#2ecc71}}
  .btn{{display:inline-block;background:#e94560;color:#fff;padding:16px 36px;border-radius:8px;font-size:17px;font-weight:bold;text-decoration:none;margin-top:16px;cursor:pointer;border:none;width:100%;text-align:center}}
  .market-data{{background:#16213e;border-left:4px solid #e94560;padding:20px 30px;border-radius:4px;margin:30px 0;font-size:15px;color:#ccc}}
  footer{{background:#0a0a15;padding:30px 20px;text-align:center;color:#555;font-size:13px;border-top:1px solid #1a1a2e}}
</style>
</head>
<body>

<!-- HERO -->
<div class="hero">
  <div class="container">
    <h1>À <span>{city}</span>, les IA recommandent vos concurrents.<br>Pas vous.</h1>
    <p>Voici les résultats d'un test répété (9 runs) + un plan clair pour corriger ça.</p>
  </div>
</div>

<!-- PREUVE -->
<section>
  <div class="container">
    <div class="proof-block">
      <h2>📊 Résultats des tests pour {company_name}</h2>
      {screenshot_block}
      <p style="color:#aaa;margin-bottom:20px">Tests réalisés sur {total_runs} runs — {models_str}</p>
      <table>
        <tr><th>Requête testée</th><th>Résultat</th></tr>
        {query_rows}
      </table>
      {competitors_block}
    </div>
  </div>
</section>

<!-- OFFRES -->
<section style="background:#0a0a15">
  <div class="container">
    <h2 style="text-align:center">Que voulez-vous faire ?</h2>
    <div class="plans">
      <div class="plan">
        <h3>Audit Complet</h3>
        <div class="price">97€ <span>une fois</span></div>
        <ul>
          <li>Rapport PDF complet</li>
          <li>Vidéo 90s personnalisée</li>
          <li>Plan d'action détaillé</li>
          <li>Checklist 8 points</li>
          <li>Livrables téléchargeables</li>
        </ul>
        <a href="#contact" class="btn">Recevoir mon audit</a>
      </div>
      <div class="plan best">
        <div class="badge">Recommandé</div>
        <h3>Kit Visibilité IA</h3>
        <div class="price">500€ <span>+ 90€/mois × 6</span></div>
        <ul>
          <li>Audit inclus</li>
          <li>Kit contenu optimisé IA</li>
          <li>Suivi mensuel 6 mois</li>
          <li>Mise à jour stratégie</li>
          <li>Accès dashboard résultats</li>
        </ul>
        <a href="#contact" class="btn">Démarrer maintenant</a>
      </div>
      <div class="plan">
        <h3>On fait tout</h3>
        <div class="price">3 500€ <span>forfait</span></div>
        <ul>
          <li>Audit + Kit inclus</li>
          <li>Rédaction contenus</li>
          <li>Optimisation site web</li>
          <li>Citations locales (20+)</li>
          <li>Garantie résultats 6 mois</li>
        </ul>
        <a href="#contact" class="btn">Me contacter</a>
      </div>
    </div>
    <p style="text-align:center;color:#666;font-size:14px;margin-top:20px">Pas d'appel requis.</p>
  </div>
</section>

<!-- DONNÉES MARCHÉ -->
<section>
  <div class="container">
    <div class="market-data">
      <strong>Pourquoi c'est urgent :</strong> En 2025, 40% des recherches locales passent par des IA (ChatGPT, Google SGE, Perplexity).
      Les entreprises qui n'apparaissent pas dans les réponses IA perdent ces clients silencieusement.
      Les algorithmes des LLMs favorisent les entreprises avec un profil web riche, des avis nombreux et des mentions croisées.
      Agir maintenant = avantage compétitif fort avant que vos concurrents s'en rendent compte.
      Délai moyen d'apparition dans les résultats IA : 2-4 mois. Les premières actions montrent des effets en 6-8 semaines.
    </div>
  </div>
</section>

<footer>
  <p>Les réponses IA peuvent varier ; résultats basés sur tests répétés horodatés ({dates_str}).</p>
  <p style="margin-top:8px">© EURKAI — Audit visibilité IA</p>
</footer>

</body>
</html>
"""

@router.get("/couvreur", response_class=HTMLResponse)
def landing_page(t: str, db: Session = Depends(get_db)):
    """Landing page personnalisée par token. URL : /couvreur?t={token}"""
    prospect = db_get_prospect_by_token(db, t)
    if not prospect:
        raise HTTPException(404, "Page introuvable")

    # Données pour le template
    from ...prospecting.generate import _runs_summary, _get_competitors
    summary     = _runs_summary(db, prospect)
    competitors = _get_competitors(prospect, 2)

    # Screenshot block
    if prospect.screenshot_url:
        screenshot_block = f'<img src="{prospect.screenshot_url}" alt="Capture test IA" class="screenshot">'
    else:
        screenshot_block = '<p style="color:#666;font-style:italic">[Capture écran à ajouter]</p>'

    # Query rows
    query_rows = ""
    for qi, (label, count) in enumerate(zip(summary["query_labels"], summary["query_mentions"])):
        if label:
            if count > 0:
                res = '<span class="cited">Cité dans les réponses IA</span>'
            else:
                res = '<span class="not-cited">Non cité — concurrent(s) prioritaire(s)</span>'
            query_rows += f"<tr><td>{label}</td><td>{res}</td></tr>\n"

    # Competitors block
    if competitors:
        comp_list = "".join(f"<li style='padding:8px 0;border-bottom:1px solid #2a2a4e;color:#e94560'>{c}</li>" for c in competitors)
        competitors_block = f"<h3 style='margin-top:30px;color:#fff'>Concurrents cités à votre place :</h3><ul style='list-style:none;padding:0'>{comp_list}</ul>"
    else:
        competitors_block = ""

    html = _LANDING_TEMPLATE.format(
        company_name=prospect.name,
        city=prospect.city,
        total_runs=summary["total_runs"],
        models_str=", ".join(summary["models"]) or "—",
        dates_str=", ".join(summary["dates"][:3]) or "—",
        screenshot_block=screenshot_block,
        query_rows=query_rows,
        competitors_block=competitors_block,
    )
    return HTMLResponse(content=html)
