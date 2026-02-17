"""
Module ASSETS GATE
POST /api/prospect/{prospect_id}/assets

- Enregistre video_url + screenshot_url
- BLOQUE READY_TO_SEND sans ces 2 champs
- Transition SCORED → READY_ASSETS → READY_TO_SEND
"""
from typing import Optional
from sqlalchemy.orm import Session

from .database import db_get_prospect, db_save_prospect
from .models import ProspectDB, ProspectStatus, AssetsInput


def set_assets(db: Session, prospect_id: str, assets: AssetsInput) -> ProspectDB:
    """Enregistre les assets et tente la transition vers READY_ASSETS."""
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise ValueError(f"Prospect {prospect_id} introuvable")

    if not assets.video_url.strip():
        raise ValueError("video_url est obligatoire")
    if not assets.screenshot_url.strip():
        raise ValueError("screenshot_url est obligatoire")

    prospect.video_url      = assets.video_url.strip()
    prospect.screenshot_url = assets.screenshot_url.strip()

    # Transition SCORED → READY_ASSETS si possible
    if prospect.status == ProspectStatus.SCORED.value:
        prospect.status = ProspectStatus.READY_ASSETS.value

    db.commit()
    db.refresh(prospect)
    return prospect


def mark_ready_to_send(db: Session, prospect_id: str) -> ProspectDB:
    """
    Tente de passer un prospect en READY_TO_SEND.
    Gate stricte : video_url + screenshot_url obligatoires + eligibility_flag = True.
    """
    prospect = db_get_prospect(db, prospect_id)
    if not prospect:
        raise ValueError(f"Prospect {prospect_id} introuvable")

    errors = []
    if not prospect.video_url:
        errors.append("video_url manquante")
    if not prospect.screenshot_url:
        errors.append("screenshot_url manquante")
    if not prospect.eligibility_flag:
        errors.append("prospect non éligible (EMAIL_OK = False)")
    if prospect.status != ProspectStatus.READY_ASSETS.value:
        errors.append(f"statut actuel '{prospect.status}' — attendu READY_ASSETS")

    if errors:
        raise ValueError("Gate READY_TO_SEND bloquée : " + " | ".join(errors))

    prospect.status = ProspectStatus.READY_TO_SEND.value
    db.commit()
    db.refresh(prospect)
    return prospect
