"""
Scheduled job registration.

KNOWN LIMITATION: APScheduler runs in-process. With more than one application
instance, every instance runs every job -- so a nightly payroll or alert sweep
would fire twice. Production needs either a single dedicated scheduler process
or a distributed lock (a row in the database claimed for the duration of the
run). This is documented rather than hidden because it is the kind of thing
that silently double-counts.
"""

import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _run(name: str, function) -> None:
    """Wrap a job so one failure never kills the scheduler thread."""
    db = SessionLocal()
    try:
        result = function(db)
        logger.info("Job %s finished: %s", name, result)
    except Exception:
        db.rollback()
        logger.exception("Job %s failed", name)
    finally:
        db.close()


def _daily_attendance(db):
    from app.tasks.attendance_jobs import run_daily_attendance

    return run_daily_attendance()


def _risk_and_alerts(db):
    from app.services import alert_engine, risk_service

    scored = risk_service.evaluate_all(db)
    fired = alert_engine.evaluate_rules(db)
    return {"risk": scored, "alerts": fired}


def _document_expiry(db):
    from app.services import document_service

    return {"expired": document_service.flag_expired(db)}


def _stability_snapshot(db):
    from app.services import stability_service

    snapshot = stability_service.compute_snapshot(db)
    return {"index": snapshot.stability_index, "grade": snapshot.grade.value}


def _housekeeping(db):
    from app.services import notification_service, report_service

    return {
        "notifications_purged": notification_service.purge_expired(db),
        "reports_purged": report_service.purge_expired(db),
    }


JOBS = [
    ("daily_attendance", _daily_attendance, CronTrigger(hour=1, minute=0)),
    ("risk_and_alerts", _risk_and_alerts, CronTrigger(hour=2, minute=0)),
    ("document_expiry", _document_expiry, CronTrigger(hour=3, minute=0)),
    # weekly, on Monday
    ("stability_snapshot", _stability_snapshot,
     CronTrigger(day_of_week="mon", hour=4, minute=0)),
    ("housekeeping", _housekeeping, CronTrigger(hour=5, minute=0)),
]


def start() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")
    for name, function, trigger in JOBS:
        _scheduler.add_job(
            _run,
            trigger=trigger,
            args=[name, function],
            id=name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,  # a missed run catches up once, not N times
        )
    _scheduler.start()
    logger.info("Scheduler started with %d job(s)", len(JOBS))
    return _scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")


def job_status() -> list:
    if _scheduler is None:
        return []
    return [
        {
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in _scheduler.get_jobs()
    ]
