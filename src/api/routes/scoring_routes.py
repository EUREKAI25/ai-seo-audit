"""
Routes Scoring
POST /api/scoring/run
GET  /api/prospect/{id}/score
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...prospecting.database import get_db, db_get_campaign, db_get_prospect, jloads
from ...prospecting.models import ScoringRunInput
from ...prospecting.scoring import run_scoring

router = APIRouter(prefix="/api", tags=["Scoring"])


@router.post("/scoring/run")
def api_scoring_run(data: ScoringRunInput, db: Session = Depends(get_db)):
    """Lance le scoring + calcul EMAIL_OK pour les prospects TESTED."""
    campaign = db_get_campaign(db, data.campaign_id)
    if not campaign:
        raise HTTPException(404, "Campagne introuvable")

    result = run_scoring(db, data.campaign_id, prospect_ids=data.prospect_ids)
    return {"campaign_id": data.campaign_id, **result}


@router.get("/prospect/{prospect_id}/score")
def api_prospect_score(prospect_id: str, db: Session = Depends(get_db)):
    """Retourne le score et la justification d'un prospect."""
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise HTTPException(404, "Prospect introuvable")

    return {
        "prospect_id":       prospect.prospect_id,
        "name":              prospect.name,
        "city":              prospect.city,
        "status":            prospect.status,
        "score":             prospect.ia_visibility_score,
        "eligibility_flag":  prospect.eligibility_flag,
        "competitors_cited": jloads(prospect.competitors_cited),
        "justification":     prospect.score_justification,
    }
