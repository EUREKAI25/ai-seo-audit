"""
Module SCHEDULER — APScheduler imposé
Europe/Rome — Mercredi, Vendredi, Dimanche : 09:00 / 13:00 / 20:30
Lundi 09:00 : prépare READY_TO_SEND (si assets présents + éligible)

Idempotent (replace_existing=True).
Tout loggé.
"""
import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
ROME_TZ = "Europe/Rome"

SCHEDULE_DAYS  = ["wed", "fri", "sun"]   # day_of_week APScheduler format
SCHEDULE_TIMES = [(9, 0), (13, 0), (20, 30)]


def _scheduled_test_run():
    """Job : lance les tests IA pour tous les prospects SCHEDULED de toutes les campagnes actives."""
    logger.info("[SCHEDULER] Lancement run IA planifié")
    try:
        from .database import SessionLocal, db_list_campaigns
        from .ia_test import run_ia_test_campaign

        db = SessionLocal()
        try:
            campaigns = db_list_campaigns(db)
            for campaign in campaigns:
                if campaign.status != "active":
                    continue
                result = run_ia_test_campaign(db, campaign.campaign_id)
                logger.info(f"[SCHEDULER] Campagne {campaign.campaign_id}: {result}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[SCHEDULER] Erreur run IA: {exc}", exc_info=True)


def _monday_prepare_ready():
    """Lundi : passage READY_TO_SEND pour les prospects READY_ASSETS éligibles."""
    logger.info("[SCHEDULER] Lundi — préparation READY_TO_SEND")
    try:
        from .database import SessionLocal, db_list_campaigns, db_list_prospects
        from .assets import mark_ready_to_send
        from .models import ProspectStatus

        db = SessionLocal()
        try:
            campaigns = db_list_campaigns(db)
            promoted = 0
            for campaign in campaigns:
                if campaign.status != "active":
                    continue
                prospects = db_list_prospects(db, campaign.campaign_id, status=ProspectStatus.READY_ASSETS.value)
                for prospect in prospects:
                    if prospect.eligibility_flag and prospect.video_url and prospect.screenshot_url:
                        try:
                            mark_ready_to_send(db, prospect.prospect_id)
                            promoted += 1
                            logger.info(f"[SCHEDULER] Prospect {prospect.prospect_id} → READY_TO_SEND")
                        except Exception as e:
                            logger.warning(f"[SCHEDULER] Prospect {prospect.prospect_id} non promu: {e}")
            logger.info(f"[SCHEDULER] Lundi: {promoted} prospect(s) promus READY_TO_SEND")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[SCHEDULER] Erreur lundi: {exc}", exc_info=True)


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone=ROME_TZ)
    return _scheduler


def start_scheduler():
    """Démarre et configure le scheduler. Idempotent."""
    sched = get_scheduler()
    if sched.running:
        logger.info("[SCHEDULER] Déjà en cours d'exécution")
        return

    # Jobs : Mer / Ven / Dim à 09:00, 13:00, 20:30
    for day in SCHEDULE_DAYS:
        for hour, minute in SCHEDULE_TIMES:
            job_id = f"ia_run_{day}_{hour:02d}{minute:02d}"
            sched.add_job(
                _scheduled_test_run,
                CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=ROME_TZ),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )
            logger.info(f"[SCHEDULER] Job ajouté: {job_id} ({day} {hour:02d}:{minute:02d} Rome)")

    # Job lundi 09:00 — préparation READY_TO_SEND
    sched.add_job(
        _monday_prepare_ready,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=ROME_TZ),
        id="monday_ready_to_send",
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
    )
    logger.info("[SCHEDULER] Job lundi 09:00 ajouté")

    sched.start()
    logger.info(f"[SCHEDULER] Démarré — {len(sched.get_jobs())} jobs configurés")


def stop_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("[SCHEDULER] Arrêté")


def scheduler_status() -> dict:
    sched = get_scheduler()
    jobs = []
    if sched.running:
        for job in sched.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
    return {"running": sched.running, "jobs": jobs}
