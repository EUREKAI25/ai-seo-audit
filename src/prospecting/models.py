"""
Data models — Campaign, ProspectRecord, TestRun
SQLAlchemy (SQLite) + Pydantic schemas + Enums statuts imposés
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ─────────────────────────── ENUMS ───────────────────────────

class ProspectStatus(str, Enum):
    SCANNED       = "SCANNED"
    SCHEDULED     = "SCHEDULED"
    TESTING       = "TESTING"
    TESTED        = "TESTED"
    SCORED        = "SCORED"
    READY_ASSETS  = "READY_ASSETS"
    READY_TO_SEND = "READY_TO_SEND"
    SENT_MANUAL   = "SENT_MANUAL"

VALID_TRANSITIONS: Dict[ProspectStatus, List[ProspectStatus]] = {
    ProspectStatus.SCANNED:       [ProspectStatus.SCHEDULED],
    ProspectStatus.SCHEDULED:     [ProspectStatus.TESTING],
    ProspectStatus.TESTING:       [ProspectStatus.TESTED],
    ProspectStatus.TESTED:        [ProspectStatus.SCORED],
    ProspectStatus.SCORED:        [ProspectStatus.READY_ASSETS],
    ProspectStatus.READY_ASSETS:  [ProspectStatus.READY_TO_SEND],
    ProspectStatus.READY_TO_SEND: [ProspectStatus.SENT_MANUAL],
    ProspectStatus.SENT_MANUAL:   [],
}

def can_transition(current: str, target: str) -> bool:
    try:
        c = ProspectStatus(current)
        t = ProspectStatus(target)
        return t in VALID_TRANSITIONS.get(c, [])
    except ValueError:
        return False

class CampaignMode(str, Enum):
    DRY_RUN    = "DRY_RUN"
    AUTO_TEST  = "AUTO_TEST"
    SEND_READY = "SEND_READY"

class AIModel(str, Enum):
    OPENAI    = "openai"
    ANTHROPIC = "anthropic"
    GEMINI    = "gemini"


# ─────────────────────────── ORM ───────────────────────────

class Base(DeclarativeBase):
    pass


class CampaignDB(Base):
    __tablename__ = "campaigns"

    campaign_id:     Mapped[str]      = mapped_column(sa.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    profession:      Mapped[str]      = mapped_column(sa.String, nullable=False)
    city:            Mapped[str]      = mapped_column(sa.String, nullable=False)
    created_at:      Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)
    timezone:        Mapped[str]      = mapped_column(sa.String, default="Europe/Rome")
    schedule_days:   Mapped[str]      = mapped_column(sa.String, default='["wednesday","friday","sunday"]')
    schedule_times:  Mapped[str]      = mapped_column(sa.String, default='["09:00","13:00","20:30"]')
    mode:            Mapped[str]      = mapped_column(sa.String, default="AUTO_TEST")
    status:          Mapped[str]      = mapped_column(sa.String, default="active")
    max_prospects:   Mapped[int]      = mapped_column(sa.Integer, default=30)

    prospects: Mapped[List["ProspectDB"]] = relationship("ProspectDB", back_populates="campaign", cascade="all, delete-orphan")
    runs:      Mapped[List["TestRunDB"]]  = relationship("TestRunDB",  back_populates="campaign", cascade="all, delete-orphan")


class ProspectDB(Base):
    __tablename__ = "prospects"

    prospect_id:          Mapped[str]           = mapped_column(sa.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id:          Mapped[str]           = mapped_column(sa.String, sa.ForeignKey("campaigns.campaign_id"), nullable=False)
    name:                 Mapped[str]           = mapped_column(sa.String, nullable=False)
    city:                 Mapped[str]           = mapped_column(sa.String, nullable=False)
    profession:           Mapped[str]           = mapped_column(sa.String, nullable=False)
    website:              Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    phone:                Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    reviews_count:        Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    google_ads_active:    Mapped[Optional[bool]]= mapped_column(sa.Boolean, nullable=True)
    competitors_cited:    Mapped[str]           = mapped_column(sa.Text, default="[]")     # JSON list[str]
    ia_visibility_score:  Mapped[Optional[float]]= mapped_column(sa.Float, nullable=True)
    eligibility_flag:     Mapped[bool]          = mapped_column(sa.Boolean, default=False)
    landing_token:        Mapped[str]           = mapped_column(sa.String, default=lambda: str(uuid.uuid4()).replace("-","")[:24])
    video_url:            Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    screenshot_url:       Mapped[Optional[str]] = mapped_column(sa.String, nullable=True)
    status:               Mapped[str]           = mapped_column(sa.String, default="SCANNED")
    score_justification:  Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at:           Mapped[datetime]      = mapped_column(sa.DateTime, default=datetime.utcnow)
    updated_at:           Mapped[datetime]      = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign: Mapped["CampaignDB"]    = relationship("CampaignDB", back_populates="prospects")
    runs:     Mapped[List["TestRunDB"]] = relationship("TestRunDB", back_populates="prospect", cascade="all, delete-orphan")


class TestRunDB(Base):
    __tablename__ = "test_runs"

    run_id:              Mapped[str]           = mapped_column(sa.String, primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id:         Mapped[str]           = mapped_column(sa.String, sa.ForeignKey("campaigns.campaign_id"), nullable=False)
    prospect_id:         Mapped[str]           = mapped_column(sa.String, sa.ForeignKey("prospects.prospect_id"), nullable=False)
    ts:                  Mapped[datetime]      = mapped_column(sa.DateTime, default=datetime.utcnow)
    model:               Mapped[str]           = mapped_column(sa.String, nullable=False)   # openai/anthropic/gemini
    queries:             Mapped[str]           = mapped_column(sa.Text, default="[]")       # JSON list[str]
    raw_answers:         Mapped[str]           = mapped_column(sa.Text, default="[]")       # JSON list[str]
    extracted_entities:  Mapped[str]           = mapped_column(sa.Text, default="[]")       # JSON list[list[dict]]
    mentioned_target:    Mapped[bool]          = mapped_column(sa.Boolean, default=False)   # True si mentionné dans ≥1 réponse
    mention_per_query:   Mapped[str]           = mapped_column(sa.Text, default="[]")       # JSON list[bool] — 1 par query
    competitors_entities:Mapped[str]           = mapped_column(sa.Text, default="[]")       # JSON list[str]
    notes:               Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    campaign: Mapped["CampaignDB"]  = relationship("CampaignDB", back_populates="runs")
    prospect: Mapped["ProspectDB"]  = relationship("ProspectDB",  back_populates="runs")


# ─────────────────────────── PYDANTIC SCHEMAS ───────────────────────────

class CampaignCreate(BaseModel):
    profession:    str
    city:          str
    max_prospects: int          = 30
    mode:          CampaignMode = CampaignMode.AUTO_TEST


class CampaignResponse(BaseModel):
    campaign_id:     str
    profession:      str
    city:            str
    created_at:      datetime
    timezone:        str
    schedule_days:   List[str]
    schedule_times:  List[str]
    mode:            str
    status:          str
    max_prospects:   int
    prospect_count:  int = 0

    class Config:
        from_attributes = True


class ProspectInput(BaseModel):
    name:              str
    city:              str
    profession:        str
    website:           Optional[str] = None
    phone:             Optional[str] = None
    reviews_count:     Optional[int] = None
    google_ads_active: Optional[bool] = None


class ProspectScanInput(BaseModel):
    city:              str
    profession:        str
    max_prospects:     int = 30
    campaign_id:       Optional[str] = None
    manual_prospects:  Optional[List[ProspectInput]] = None


class ProspectResponse(BaseModel):
    prospect_id:         str
    campaign_id:         str
    name:                str
    city:                str
    profession:          str
    website:             Optional[str]
    phone:               Optional[str]
    reviews_count:       Optional[int]
    google_ads_active:   Optional[bool]
    competitors_cited:   List[str]
    ia_visibility_score: Optional[float]
    eligibility_flag:    bool
    landing_token:       str
    video_url:           Optional[str]
    screenshot_url:      Optional[str]
    status:              str
    score_justification: Optional[str]

    class Config:
        from_attributes = True


class IATestRunInput(BaseModel):
    campaign_id:  str
    prospect_ids: Optional[List[str]] = None   # None = all SCHEDULED in campaign


class AssetsInput(BaseModel):
    video_url:      str
    screenshot_url: str


class ScoringRunInput(BaseModel):
    campaign_id:  str
    prospect_ids: Optional[List[str]] = None


class GenerateInput(BaseModel):
    campaign_id:  str
    prospect_ids: Optional[List[str]] = None   # None = all SCORED+eligible
