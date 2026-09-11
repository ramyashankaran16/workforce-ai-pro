"""
Audit and activity logging.

Audit rows are append-only: there is no update or delete path in this module,
and none should be added. An audit trail that can be edited is not an audit
trail. Tamper-evidence beyond that is a database-permissions question, not an
application one -- the honest position is that an admin with direct database
access can still alter rows, and the mitigation is restricting that access.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.audit import ActivityLog, AuditLog, LoginHistory
from app.models.enums import AuditAction
from app.models.user import User
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

# Field names whose values must never be written to the audit trail.
REDACTED_FIELDS = {
    "password", "hashed_password", "new_password", "current_password",
    "token", "access_token", "refresh_token", "secret", "api_key",
    "bank_account_number", "pan_number", "ifsc_code",
}


def redact(values: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not values:
        return values
    return {
        key: ("***redacted***" if key.lower() in REDACTED_FIELDS else value)
        for key, value in values.items()
    }


def record(
    db: Session,
    action: AuditAction,
    entity_type: str,
    entity_id: Optional[int] = None,
    user: Optional[User] = None,
    description: Optional[str] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    endpoint: Optional[str] = None,
    http_method: Optional[str] = None,
    status_code: Optional[int] = None,
    duration_ms: Optional[float] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    is_successful: bool = True,
    error_message: Optional[str] = None,
    commit: bool = True,
) -> AuditLog:
    old_clean = redact(old_values)
    new_clean = redact(new_values)

    changed = None
    if old_clean and new_clean:
        changed = {
            "fields": sorted(
                key for key in new_clean
                if key in old_clean and old_clean[key] != new_clean[key]
            )
        }

    entry = AuditLog(
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        user_role=user.role_name if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        old_values=old_clean,
        new_values=new_clean,
        changed_fields=changed,
        endpoint=endpoint,
        http_method=http_method,
        status_code=status_code,
        duration_ms=duration_ms,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:300] or None,
        is_successful=is_successful,
        error_message=error_message,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def log_activity(
    db: Session,
    activity_type: str,
    title: str,
    description: Optional[str] = None,
    module: Optional[str] = None,
    user_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> ActivityLog:
    entry = ActivityLog(
        user_id=user_id,
        employee_id=employee_id,
        activity_type=activity_type,
        title=title,
        description=description,
        module=module,
        reference_type=reference_type,
        reference_id=reference_id,
        extra_data=extra,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def entity_trail(db: Session, entity_type: str, entity_id: int) -> List[AuditLog]:
    return (
        db.execute(
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
        )
        .scalars()
        .all()
    )


def summary(db: Session, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)

    by_action = db.execute(
        select(AuditLog.action, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
    ).all()

    by_entity = db.execute(
        select(AuditLog.entity_type, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since)
        .group_by(AuditLog.entity_type)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    ).all()

    busiest = db.execute(
        select(AuditLog.user_email, func.count(AuditLog.id))
        .where(AuditLog.created_at >= since, AuditLog.user_email.isnot(None))
        .group_by(AuditLog.user_email)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    ).all()

    failures = db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.created_at >= since, AuditLog.is_successful.is_(False)
        )
    ).scalar() or 0

    failed_logins = db.execute(
        select(func.count(LoginHistory.id)).where(
            LoginHistory.logged_in_at >= since,
            LoginHistory.is_successful.is_(False),
        )
    ).scalar() or 0

    return {
        "window_days": days,
        "total_entries": int(
            db.execute(
                select(func.count(AuditLog.id)).where(AuditLog.created_at >= since)
            ).scalar()
            or 0
        ),
        "failed_operations": int(failures),
        "failed_logins": int(failed_logins),
        "by_action": {
            str(a.value if hasattr(a, "value") else a): int(c) for a, c in by_action
        },
        "by_entity": {str(e): int(c) for e, c in by_entity},
        "most_active_users": [
            {"email": email, "operations": int(count)} for email, count in busiest
        ],
    }


def suspicious_logins(db: Session, threshold: int = 5, hours: int = 24) -> List[dict]:
    """Emails with repeated failures in a short window."""
    since = utcnow() - timedelta(hours=hours)
    rows = db.execute(
        select(
            LoginHistory.email_attempted,
            func.count(LoginHistory.id),
            func.max(LoginHistory.logged_in_at),
        )
        .where(
            LoginHistory.logged_in_at >= since,
            LoginHistory.is_successful.is_(False),
        )
        .group_by(LoginHistory.email_attempted)
        .having(func.count(LoginHistory.id) >= threshold)
    ).all()

    return [
        {
            "email": email,
            "failed_attempts": int(count),
            "last_attempt": last,
            "window_hours": hours,
        }
        for email, count, last in rows
    ]
