"""
SQLite — init + session + helpers CRUD
"""
import json
import os
from pathlib import Path
from typing import Optional, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .models import Base, CampaignDB, ProspectDB, TestRunDB, ProspectStatus, can_transition

# ── Config ──
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH   = os.getenv("PROSPECTING_DB_PATH", str(DATA_DIR / "prospecting.db"))
ENGINE    = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def init_db() -> None:
    Base.metadata.create_all(bind=ENGINE)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── CRUD Campaign ──

def db_create_campaign(db: Session, obj: CampaignDB) -> CampaignDB:
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def db_get_campaign(db: Session, campaign_id: str) -> Optional[CampaignDB]:
    return db.query(CampaignDB).filter(CampaignDB.campaign_id == campaign_id).first()


def db_list_campaigns(db: Session) -> List[CampaignDB]:
    return db.query(CampaignDB).order_by(CampaignDB.created_at.desc()).all()


# ── CRUD Prospect ──

def db_create_prospect(db: Session, obj: ProspectDB) -> ProspectDB:
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def db_get_prospect(db: Session, prospect_id: str) -> Optional[ProspectDB]:
    return db.query(ProspectDB).filter(ProspectDB.prospect_id == prospect_id).first()


def db_get_prospect_by_token(db: Session, token: str) -> Optional[ProspectDB]:
    return db.query(ProspectDB).filter(ProspectDB.landing_token == token).first()


def db_list_prospects(db: Session, campaign_id: str, status: Optional[str] = None) -> List[ProspectDB]:
    q = db.query(ProspectDB).filter(ProspectDB.campaign_id == campaign_id)
    if status:
        q = q.filter(ProspectDB.status == status)
    return q.order_by(ProspectDB.ia_visibility_score.desc().nullslast()).all()


def db_update_prospect_status(db: Session, prospect: ProspectDB, new_status: str) -> bool:
    if not can_transition(prospect.status, new_status):
        return False
    prospect.status = new_status
    db.commit()
    return True


def db_save_prospect(db: Session, prospect: ProspectDB) -> ProspectDB:
    db.commit()
    db.refresh(prospect)
    return prospect


# ── CRUD TestRun ──

def db_create_run(db: Session, obj: TestRunDB) -> TestRunDB:
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def db_list_runs(db: Session, prospect_id: str) -> List[TestRunDB]:
    return db.query(TestRunDB).filter(TestRunDB.prospect_id == prospect_id).order_by(TestRunDB.ts).all()


# ── JSON helpers (for JSON columns) ──

def jloads(s: str) -> list:
    try:
        return json.loads(s) if s else []
    except Exception:
        return []


def jdumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
