"""
Routes Campagne
POST /api/campaign/create
GET  /api/campaign/{id}/status
GET  /api/campaigns
POST /api/prospect-scan
POST /api/prospect-scan/csv   (upload CSV)
"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ...prospecting.database import get_db, db_get_campaign, db_list_campaigns, jloads
from ...prospecting.models import CampaignCreate, ProspectScanInput
from ...prospecting.prospect_scan import create_campaign, scan_prospects, load_from_csv

router = APIRouter(prefix="/api", tags=["Campaign & Prospects"])


@router.post("/campaign/create")
def api_create_campaign(data: CampaignCreate, db: Session = Depends(get_db)):
    """Crée une campagne avec le scheduling imposé."""
    campaign = create_campaign(db, data)
    return {
        "campaign_id": campaign.campaign_id,
        "profession":  campaign.profession,
        "city":        campaign.city,
        "mode":        campaign.mode,
        "schedule":    {
            "days":  jloads(campaign.schedule_days),
            "times": jloads(campaign.schedule_times),
            "timezone": campaign.timezone,
        },
        "status": campaign.status,
    }


@router.get("/campaign/{campaign_id}/status")
def api_campaign_status(campaign_id: str, db: Session = Depends(get_db)):
    """Statut d'une campagne + compteurs prospects."""
    campaign = db_get_campaign(db, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campagne introuvable")

    from ...prospecting.database import db_list_prospects
    from ...prospecting.scheduler import scheduler_status

    prospects = db_list_prospects(db, campaign_id)
    status_counts = {}
    for p in prospects:
        status_counts[p.status] = status_counts.get(p.status, 0) + 1

    return {
        "campaign_id":    campaign.campaign_id,
        "profession":     campaign.profession,
        "city":           campaign.city,
        "mode":           campaign.mode,
        "status":         campaign.status,
        "total_prospects": len(prospects),
        "by_status":      status_counts,
        "eligible":       sum(1 for p in prospects if p.eligibility_flag),
        "scheduler":      scheduler_status(),
    }


@router.get("/campaigns")
def api_list_campaigns(db: Session = Depends(get_db)):
    campaigns = db_list_campaigns(db)
    return [
        {
            "campaign_id": c.campaign_id,
            "profession":  c.profession,
            "city":        c.city,
            "mode":        c.mode,
            "status":      c.status,
            "created_at":  c.created_at.isoformat(),
            "prospect_count": len(c.prospects),
        }
        for c in campaigns
    ]


@router.post("/prospect-scan")
def api_prospect_scan(data: ProspectScanInput, db: Session = Depends(get_db)):
    """
    Scanne et importe des prospects.
    Fournir manual_prospects dans le body OU utiliser /prospect-scan/csv.
    """
    try:
        prospects = scan_prospects(db, data)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {
        "campaign_id":    prospects[0].campaign_id if prospects else None,
        "created":        len(prospects),
        "prospects":      [
            {
                "prospect_id": p.prospect_id,
                "name":        p.name,
                "city":        p.city,
                "website":     p.website,
                "status":      p.status,
            }
            for p in prospects
        ],
    }


@router.post("/prospect-scan/csv")
async def api_prospect_scan_csv(
    city: str,
    profession: str,
    max_prospects: int = 30,
    campaign_id: str = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Import prospects depuis un CSV.
    Colonnes : name, website, phone, reviews_count, google_ads_active
    """
    content = (await file.read()).decode("utf-8")
    manual = load_from_csv(content, city, profession)

    if not manual:
        raise HTTPException(400, "CSV vide ou format invalide (colonne 'name' requise)")

    data = ProspectScanInput(
        city=city,
        profession=profession,
        max_prospects=max_prospects,
        campaign_id=campaign_id,
        manual_prospects=manual[:max_prospects],
    )
    try:
        prospects = scan_prospects(db, data)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"created": len(prospects), "campaign_id": prospects[0].campaign_id if prospects else None}
