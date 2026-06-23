"""Programacion de reportes periodicos con APScheduler.

Arranca junto con la app (ver main.py). Segun la config:
  - monthly  -> dia REPORT_DAY_OF_MONTH a las REPORT_HOUR:00
  - weekly   -> dia REPORT_DAY_OF_WEEK a las REPORT_HOUR:00

Genera el reporte del periodo y lo guarda automaticamente.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .database import SessionLocal
from .service import generate_and_store

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scheduled_job() -> None:
    """Job que genera el reporte programado del tenant por defecto."""
    logger.info("Ejecutando reporte programado...")
    db = SessionLocal()
    try:
        report = generate_and_store(db, tenant_id=1, send_email=True)
        logger.info("Reporte programado generado: %s (%s)", report.filename, report.status)
    except Exception as exc:  # noqa: BLE001 - el scheduler no debe morir por un fallo
        logger.error("Fallo el reporte programado: %s", exc)
    finally:
        db.close()


def _build_trigger() -> CronTrigger:
    hour = settings.report_hour
    if settings.report_schedule == "weekly":
        return CronTrigger(day_of_week=settings.report_day_of_week, hour=hour, minute=0)
    # monthly por defecto
    return CronTrigger(day=settings.report_day_of_month, hour=hour, minute=0)


def start_scheduler() -> BackgroundScheduler:
    """Inicia el scheduler (idempotente)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    trigger = _build_trigger()
    _scheduler.add_job(
        _scheduled_job,
        trigger=trigger,
        id="periodic_report",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info(
        "Scheduler iniciado (%s, hora %02d:00 UTC).",
        settings.report_schedule,
        settings.report_hour,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido.")
