"""FastAPI — application principale.
Combine : audit B2C (existant) + pipeline prospection B2B (nouveau)
"""
import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI SEO Audit API",
    description="Audit de visibilité IA + Pipeline prospection B2B",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static + Templates ──
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")


# ── DB init au démarrage ──
@app.on_event("startup")
def startup():
    from ..prospecting.database import init_db
    init_db()
    logger.info("Base de données prospecting initialisée (SQLite)")

    # Démarrer le scheduler
    from ..prospecting.scheduler import start_scheduler
    start_scheduler()
    logger.info("Scheduler APScheduler démarré")


@app.on_event("shutdown")
def shutdown():
    from ..prospecting.scheduler import stop_scheduler
    stop_scheduler()


# ── Routes B2C (existantes) ──
@app.get("/")
async def landing_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/success")
async def success_page(request: Request, audit_id: str = None):
    return templates.TemplateResponse("success.html", {"request": request, "audit_id": audit_id})


@app.get("/health")
async def health():
    from ..prospecting.scheduler import scheduler_status
    return {
        "status":    "healthy",
        "service":   "ai-seo-audit-api",
        "version":   "2.0.0",
        "scheduler": scheduler_status(),
    }


# ── Routes B2B — Pipeline prospection ──
from .routes.campaign       import router as campaign_router
from .routes.ia_test_routes import router as ia_test_router
from .routes.scoring_routes import router as scoring_router
from .routes.generate_routes import router as generate_router
from .routes.admin          import router as admin_router

app.include_router(campaign_router)
app.include_router(ia_test_router)
app.include_router(scoring_router)
app.include_router(generate_router)
app.include_router(admin_router)

# ── Routes B2C (existantes si disponibles) ──
try:
    from .routes.audit   import router as audit_router
    from .routes.payment import router as payment_router
    from .routes.export  import router as export_router
    app.include_router(audit_router,   prefix="/api/audit",   tags=["Audit B2C"])
    app.include_router(payment_router, prefix="/api/payment", tags=["Payment"])
    app.include_router(export_router,  prefix="/api/export",  tags=["Export"])
except ImportError:
    logger.warning("Routes B2C non disponibles (modules manquants) — pipeline B2B seul actif")
