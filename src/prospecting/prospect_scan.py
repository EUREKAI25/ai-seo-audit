"""
Module PROSPECT_SCAN
POST /api/prospect-scan
Input : {city, profession, max_prospects, campaign_id?, manual_prospects?}
Output: ProspectRecord[] stockés en DB

MVP : accepte une liste manuelle OU un CSV/JSON fourni.
Aucun paramètre libre hors (city, profession, max_prospects).
"""
import csv
import io
import json
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from .database import db_create_campaign, db_create_prospect, db_list_prospects, jdumps
from .models import (
    CampaignDB, CampaignCreate, CampaignMode,
    ProspectDB, ProspectInput, ProspectScanInput, ProspectStatus
)


# ── Queries imposées par profession ──

QUERIES_BY_PROFESSION = {
    "couvreur": [
        "Quel est le meilleur couvreur à {city} ?",
        "Couvreur recommandé à {city}",
        "Entreprise fiable pour réparation toiture {city}",
        "Qui contacter pour fuite toiture à {city} ?",
        "Couvreur urgent {city} avis",
    ],
    "plombier": [
        "Meilleur plombier à {city} ?",
        "Plombier recommandé à {city}",
        "Dépannage plomberie urgence {city}",
        "Qui appeler pour fuite d'eau à {city} ?",
        "Plombier {city} avis fiable",
    ],
    "electricien": [
        "Meilleur électricien à {city} ?",
        "Électricien recommandé {city}",
        "Dépannage électrique urgent {city}",
        "Qui contacter panne électrique {city} ?",
        "Électricien {city} avis certifié",
    ],
    "default": [
        "Meilleur {profession} à {city} ?",
        "{profession} recommandé à {city}",
        "Entreprise fiable {profession} {city}",
        "Qui contacter pour {profession} à {city} ?",
        "{profession} {city} avis",
    ],
}


def get_queries(profession: str, city: str) -> List[str]:
    """Retourne les 5 requêtes imposées pour la profession/ville."""
    templates = QUERIES_BY_PROFESSION.get(profession.lower(), QUERIES_BY_PROFESSION["default"])
    return [t.format(profession=profession, city=city) for t in templates]


# ── Création campagne ──

def create_campaign(db: Session, data: CampaignCreate) -> CampaignDB:
    campaign = CampaignDB(
        campaign_id=str(uuid.uuid4()),
        profession=data.profession,
        city=data.city,
        max_prospects=data.max_prospects,
        mode=data.mode.value,
        schedule_days=jdumps(["wednesday", "friday", "sunday"]),
        schedule_times=jdumps(["09:00", "13:00", "20:30"]),
        timezone="Europe/Rome",
        status="active",
    )
    return db_create_campaign(db, campaign)


# ── Scan prospects ──

def scan_prospects(
    db: Session,
    data: ProspectScanInput,
) -> List[ProspectDB]:
    """
    Crée ou récupère la campagne, puis insère les prospects.
    Sources (par ordre de priorité) :
      1. data.manual_prospects (liste JSON dans le body)
      2. Placeholder auto-généré si rien n'est fourni
    """
    # Récupérer ou créer la campagne
    from .database import db_get_campaign
    if data.campaign_id:
        campaign = db_get_campaign(db, data.campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {data.campaign_id} introuvable")
    else:
        campaign = create_campaign(
            db,
            CampaignCreate(
                profession=data.profession,
                city=data.city,
                max_prospects=data.max_prospects,
            ),
        )

    inputs: List[ProspectInput] = []

    if data.manual_prospects:
        inputs = data.manual_prospects[: data.max_prospects]
    else:
        # Fallback : placeholder — signale que l'utilisateur doit fournir sa liste
        inputs = _placeholder_prospects(data.city, data.profession, min(data.max_prospects, 3))

    created: List[ProspectDB] = []
    for inp in inputs:
        prospect = ProspectDB(
            prospect_id=str(uuid.uuid4()),
            campaign_id=campaign.campaign_id,
            name=inp.name,
            city=inp.city or data.city,
            profession=inp.profession or data.profession,
            website=inp.website,
            phone=inp.phone,
            reviews_count=inp.reviews_count,
            google_ads_active=inp.google_ads_active,
            competitors_cited=jdumps([]),
            eligibility_flag=False,
            status=ProspectStatus.SCANNED.value,
        )
        created.append(db_create_prospect(db, prospect))

    # Passer SCHEDULED pour démarrer le scheduling
    for p in created:
        p.status = ProspectStatus.SCHEDULED.value
    db.commit()

    return created


def load_from_csv(csv_content: str, city: str, profession: str) -> List[ProspectInput]:
    """
    Parse un CSV avec colonnes : name, website, phone, reviews_count, google_ads_active
    Colonnes minimales requises : name
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    prospects = []
    for row in reader:
        try:
            p = ProspectInput(
                name=row.get("name", "").strip(),
                city=row.get("city", city).strip() or city,
                profession=row.get("profession", profession).strip() or profession,
                website=row.get("website", "").strip() or None,
                phone=row.get("phone", "").strip() or None,
                reviews_count=int(row["reviews_count"]) if row.get("reviews_count", "").strip().isdigit() else None,
                google_ads_active=row.get("google_ads_active", "").strip().lower() in ("true", "1", "oui"),
            )
            if p.name:
                prospects.append(p)
        except Exception:
            continue
    return prospects


def _placeholder_prospects(city: str, profession: str, count: int) -> List[ProspectInput]:
    """Génère des prospects placeholder — à remplacer par une vraie liste."""
    return [
        ProspectInput(
            name=f"[PLACEHOLDER] {profession.title()} {i+1} {city}",
            city=city,
            profession=profession,
        )
        for i in range(count)
    ]
