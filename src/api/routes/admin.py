"""
Admin UI — /admin/campaign/{id}
Guard : ADMIN_TOKEN (header X-Admin-Token ou query param token)
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ...prospecting.database import get_db, db_get_campaign, db_list_prospects, jloads
from ...prospecting.models import ProspectStatus, AssetsInput
from ...prospecting.assets import set_assets, mark_ready_to_send
from ...prospecting.generate import landing_url

router = APIRouter(prefix="/admin", tags=["Admin"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme-admin-token")


def _check_auth(request: Request):
    token = (
        request.headers.get("X-Admin-Token")
        or request.query_params.get("token")
    )
    if token != ADMIN_TOKEN:
        raise HTTPException(401, "Non autorisé — X-Admin-Token invalide")


_ADMIN_CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',sans-serif;background:#f4f6fb;color:#1a1a2e;padding:30px}
h1{color:#1a1a2e;margin-bottom:6px;font-size:26px}
.meta{color:#666;font-size:14px;margin-bottom:30px}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08)}
th{background:#1a1a2e;color:#fff;padding:12px 16px;font-size:13px;text-align:left;font-weight:600}
td{padding:11px 16px;border-bottom:1px solid #edf0f7;font-size:14px;vertical-align:middle}
tr:hover{background:#f8faff}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:bold}
.badge-SCANNED{background:#dde;color:#445}
.badge-SCHEDULED{background:#ddf;color:#336}
.badge-TESTING{background:#ffd;color:#663}
.badge-TESTED{background:#d5f5e3;color:#1e8449}
.badge-SCORED{background:#e8daef;color:#6c3483}
.badge-READY_ASSETS{background:#fde8d8;color:#b03a2e}
.badge-READY_TO_SEND{background:#d0f0d0;color:#196f3d}
.badge-SENT_MANUAL{background:#ccc;color:#555}
.score{font-weight:bold;color:#e94560;font-size:18px}
.eligible{color:#1e8449;font-weight:bold}
.not-eligible{color:#aaa;font-size:12px}
form.inline{display:inline}
input[type=url]{padding:5px 8px;border:1px solid #ccc;border-radius:4px;font-size:13px;width:200px}
.btn{padding:6px 14px;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:600}
.btn-primary{background:#1a1a2e;color:#fff}
.btn-green{background:#27ae60;color:#fff}
.btn-red{background:#e94560;color:#fff}
.btn:hover{opacity:.85}
.stats{display:flex;gap:20px;margin-bottom:30px;flex-wrap:wrap}
.stat{background:#fff;border-radius:8px;padding:16px 24px;border-left:4px solid #e94560;box-shadow:0 2px 6px rgba(0,0,0,.06)}
.stat .num{font-size:32px;font-weight:bold;color:#e94560}
.stat .lbl{font-size:13px;color:#666;margin-top:4px}
</style>
"""

def _build_admin_page(campaign, prospects) -> str:
    stats = {
        "total": len(prospects),
        "eligible": sum(1 for p in prospects if p.eligibility_flag),
        "ready": sum(1 for p in prospects if p.status == ProspectStatus.READY_TO_SEND.value),
        "scored": sum(1 for p in prospects if p.status in [ProspectStatus.SCORED.value, ProspectStatus.READY_ASSETS.value, ProspectStatus.READY_TO_SEND.value]),
    }

    rows = ""
    for p in sorted(prospects, key=lambda x: (x.ia_visibility_score or 0), reverse=True):
        badge  = f'<span class="badge badge-{p.status}">{p.status}</span>'
        score  = f'<span class="score">{p.ia_visibility_score:.1f}/10</span>' if p.ia_visibility_score is not None else "—"
        elig   = '<span class="eligible">✓ EMAIL OK</span>' if p.eligibility_flag else '<span class="not-eligible">✗</span>'
        comps  = ", ".join(jloads(p.competitors_cited)[:2]) or "—"
        l_url  = f'<a href="{landing_url(p)}" target="_blank" style="font-size:12px">🔗 landing</a>' if p.eligibility_flag else ""

        # Formulaire assets
        asset_form = f"""
        <form method="post" action="/admin/prospect/{p.prospect_id}/assets" class="inline">
          <input type="url" name="video_url" value="{p.video_url or ''}" placeholder="video_url" required>
          <input type="url" name="screenshot_url" value="{p.screenshot_url or ''}" placeholder="screenshot_url" required>
          <button class="btn btn-primary" type="submit">Sauvegarder</button>
        </form>"""

        # Bouton mark ready
        if p.status == ProspectStatus.READY_ASSETS.value and p.eligibility_flag:
            ready_btn = f"""
            <form method="post" action="/admin/prospect/{p.prospect_id}/mark-ready" class="inline">
              <button class="btn btn-green" type="submit">▶ READY_TO_SEND</button>
            </form>"""
        else:
            ready_btn = ""

        rows += f"""
        <tr>
          <td><strong>{p.name}</strong><br><small style="color:#888">{p.website or '—'}</small></td>
          <td>{score}</td>
          <td>{elig}</td>
          <td>{badge}</td>
          <td>{comps}</td>
          <td>{asset_form}</td>
          <td>{ready_btn} {l_url}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Admin — {campaign.profession} {campaign.city}</title>
{_ADMIN_CSS}</head><body>
<h1>🎯 Campagne — {campaign.profession.title()} à {campaign.city}</h1>
<p class="meta">ID: {campaign.campaign_id} | Mode: {campaign.mode} | Timezone: {campaign.timezone}</p>
<div class="stats">
  <div class="stat"><div class="num">{stats['total']}</div><div class="lbl">Prospects</div></div>
  <div class="stat"><div class="num">{stats['scored']}</div><div class="lbl">Scorés</div></div>
  <div class="stat"><div class="num">{stats['eligible']}</div><div class="lbl">Éligibles</div></div>
  <div class="stat"><div class="num">{stats['ready']}</div><div class="lbl">Ready to Send</div></div>
</div>
<table>
  <tr>
    <th>Prospect</th><th>Score</th><th>Email OK</th><th>Statut</th>
    <th>Concurrents</th><th>Assets (video / screenshot)</th><th>Actions</th>
  </tr>
  {rows}
</table>
<p style="margin-top:20px;font-size:13px;color:#999">
  <a href="/api/generate/campaign" style="color:#e94560">Générer SendQueue</a> |
  <a href="/api/campaign/{campaign.campaign_id}/status" style="color:#e94560">API status</a>
</p>
</body></html>"""


@router.get("/campaign/{campaign_id}", response_class=HTMLResponse)
def admin_campaign(campaign_id: str, request: Request, db: Session = Depends(get_db)):
    _check_auth(request)
    campaign = db_get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campagne introuvable")
    prospects = db_list_prospects(db, campaign_id)
    return HTMLResponse(content=_build_admin_page(campaign, prospects))


@router.post("/prospect/{prospect_id}/assets")
async def admin_set_assets(
    prospect_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_auth(request)
    form = await request.form()
    assets = AssetsInput(
        video_url=form.get("video_url", ""),
        screenshot_url=form.get("screenshot_url", ""),
    )
    try:
        prospect = set_assets(db, prospect_id, assets)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Redirect vers l'admin de la campagne
    return RedirectResponse(
        f"/admin/campaign/{prospect.campaign_id}?token={request.query_params.get('token', '')}",
        status_code=303,
    )


@router.post("/prospect/{prospect_id}/mark-ready")
async def admin_mark_ready(
    prospect_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _check_auth(request)
    try:
        prospect = mark_ready_to_send(db, prospect_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return RedirectResponse(
        f"/admin/campaign/{prospect.campaign_id}?token={request.query_params.get('token', '')}",
        status_code=303,
    )


@router.get("/campaigns", response_class=HTMLResponse)
def admin_list_campaigns(request: Request, db: Session = Depends(get_db)):
    _check_auth(request)
    from ...prospecting.database import db_list_campaigns
    campaigns = db_list_campaigns(db)
    token = request.query_params.get("token", "")
    rows = "".join(
        f'<tr><td><a href="/admin/campaign/{c.campaign_id}?token={token}">{c.profession} — {c.city}</a></td>'
        f'<td>{c.mode}</td><td>{len(c.prospects)}</td><td>{c.created_at.strftime("%d/%m/%Y")}</td></tr>'
        for c in campaigns
    )
    return HTMLResponse(f"""<!DOCTYPE html><html><head>{_ADMIN_CSS}<title>Admin</title></head>
    <body><h1>Campagnes</h1><table>
    <tr><th>Campagne</th><th>Mode</th><th>Prospects</th><th>Créée</th></tr>{rows}
    </table></body></html>""")
