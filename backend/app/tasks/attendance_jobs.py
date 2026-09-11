"""
Nightly attendance jobs.

Order matters: forgotten check-outs are closed first, so the daily marking pass
does not see an open record and mark that person absent.
"""

import logging
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.services import attendance_service

logger = logging.getLogger(__name__)


def run_daily_attendance(on: date = None) -> dict:
    """Close open records, then stamp weekend / holiday / leave / absent."""
    target = on or (date.today() - timedelta(days=1))
    db = SessionLocal()
    try:
        closed = attendance_service.close_forgotten_checkouts(db, target)
        counts = attendance_service.mark_daily_attendance(db, target)
        logger.info(
            "Attendance for %s: %s auto-closed, %s", target, closed, counts
        )
        return {"date": target.isoformat(), "auto_closed": closed, **counts}
    except Exception:
        db.rollback()
        logger.exception("Daily attendance job failed for %s", target)
        raise
    finally:
        db.close()
