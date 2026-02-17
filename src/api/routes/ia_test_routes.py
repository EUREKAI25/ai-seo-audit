"""
Routes IA Test
POST /api/ia-test/run
GET  /api/prospect/{id}/runs
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...prospecting.database import get_db, db_get_campaign, db_list_runs, jloads
from ...prospecting.models import IATestRunInput
from ...prospecting.ia_test import run_ia_test_campaign, get_active_models

router = APIRouter(prefix="/api", tags=["IA Tests"])


@router.post("/ia-test/run")
def api_ia_test_run(
    data: IATestRunInput,
    dry_run: bool = Query(False, description="Simule sans appeler les APIs IA"),
    db: Session = Depends(get_db),
):
    """
    Lance 1 run IA sur les prospects SCHEDULED de la campagne.
    dry_run=true : génère les structures sans appels API.
    """
    campaign = db_get_campaign(db, data.campaign_id)
    if not campaign:
        raise HTTPException(404, "Campagne introuvable")

    active_models = get_active_models()
    if not active_models and not dry_run:
        raise HTTPException(400, "Aucune clé API IA configurée (OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY)")

    result = run_ia_test_campaign(
        db,
        data.campaign_id,
        prospect_ids=data.prospect_ids,
        dry_run=dry_run,
    )
    return {
        "campaign_id":   data.campaign_id,
        "dry_run":       dry_run,
        "models_active": active_models if not dry_run else ["openai", "anthropic", "gemini"],
        **result,
    }


@router.get("/prospect/{prospect_id}/runs")
def api_prospect_runs(prospect_id: str, db: Session = Depends(get_db)):
    """Retourne tous les runs d'un prospect."""
    from ...prospecting.database import db_get_prospect
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect introuvable")

    runs = db_list_runs(db, prospect_id)
    return {
        "prospect_id": prospect_id,
        "total_runs":  len(runs),
        "runs": [
            {
                "run_id":          r.run_id,
                "model":           r.model,
                "ts":              r.ts.isoformat(),
                "mentioned_target":r.mentioned_target,
                "mention_per_query": jloads(r.mention_per_query),
                "competitors":     jloads(r.competitors_entities)[:5],
                "notes":           r.notes,
            }
            for r in runs
        ],
    }
