"""
Notification creation, preference filtering and fan-out.

Preferences are checked per category and per channel, so a user who has turned
off payroll email still gets payroll in-app. A notification nobody wants is
worse than none: it trains people to ignore the bell.
"""

import logging
from datetime import timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.employee import Employee
from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    Priority,
)
from app.models.notification import Notification, NotificationPreference
from app.models.role import Role
from app.models.user import User
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 60


def _channel_enabled(
    db: Session, user_id: int, category: NotificationCategory,
    channel: NotificationChannel,
) -> bool:
    preference = db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
    ).scalar_one_or_none()

    if preference is None:
        # No row means defaults: in-app and email on, SMS off.
        return channel != NotificationChannel.SMS

    return {
        NotificationChannel.IN_APP: preference.in_app_enabled,
        NotificationChannel.EMAIL: preference.email_enabled,
        NotificationChannel.SMS: preference.sms_enabled,
    }.get(channel, True)


def notify(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    category: NotificationCategory = NotificationCategory.SYSTEM,
    notification_type: NotificationType = NotificationType.INFO,
    priority: Priority = Priority.MEDIUM,
    channel: NotificationChannel = NotificationChannel.IN_APP,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    action_url: Optional[str] = None,
    commit: bool = True,
) -> Optional[Notification]:
    """Create one notification, honouring the recipient's preferences."""
    if not _channel_enabled(db, user_id, category, channel):
        return None

    record = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        notification_type=notification_type,
        priority=priority,
        channel=channel,
        reference_type=reference_type,
        reference_id=reference_id,
        action_url=action_url,
        expires_at=utcnow() + timedelta(days=DEFAULT_TTL_DAYS),
    )
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
    return record


def notify_many(
    db: Session, user_ids: Sequence[int], **kwargs
) -> int:
    """Fan out to several users in one transaction."""
    sent = 0
    for user_id in set(user_ids):
        if notify(db, user_id, commit=False, **kwargs):
            sent += 1
    db.commit()
    return sent


def notify_roles(db: Session, role_names: Iterable[str], **kwargs) -> int:
    users = (
        db.execute(
            select(User.id)
            .join(Role)
            .where(Role.name.in_(list(role_names)), User.is_deleted.is_(False))
        )
        .scalars()
        .all()
    )
    return notify_many(db, users, **kwargs)


def notify_manager_of(db: Session, employee_id: int, **kwargs) -> bool:
    employee = db.get(Employee, employee_id)
    if employee is None or not employee.manager_id:
        return False
    manager = db.get(Employee, employee.manager_id)
    if manager is None or not manager.user_id:
        return False
    return notify(db, manager.user_id, **kwargs) is not None


def unread_count(db: Session, user_id: int) -> Dict[str, int]:
    total = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).scalar() or 0

    by_priority = db.execute(
        select(Notification.priority, func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .group_by(Notification.priority)
    ).all()

    return {
        "unread": int(total),
        "by_priority": {
            str(priority.value if hasattr(priority, "value") else priority): int(count)
            for priority, count in by_priority
        },
    }


def mark_read(db: Session, notification_id: int, user_id: int) -> Notification:
    record = db.get(Notification, notification_id)
    if record is None or record.user_id != user_id:
        raise NotFoundError("Notification not found.")
    if not record.is_read:
        record.is_read = True
        record.read_at = utcnow()
        db.commit()
        db.refresh(record)
    return record


def mark_all_read(db: Session, user_id: int) -> int:
    rows = (
        db.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.is_read = True
        row.read_at = utcnow()
    db.commit()
    return len(rows)


def set_preferences(db: Session, user_id: int, entries: List[dict]) -> List[NotificationPreference]:
    out = []
    for entry in entries:
        preference = db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category == entry["category"],
            )
        ).scalar_one_or_none()

        if preference is None:
            preference = NotificationPreference(
                user_id=user_id, category=entry["category"]
            )
            db.add(preference)

        for field in ("in_app_enabled", "email_enabled", "sms_enabled"):
            if field in entry and entry[field] is not None:
                setattr(preference, field, entry[field])
        out.append(preference)

    db.commit()
    for preference in out:
        db.refresh(preference)
    return out


def list_preferences(db: Session, user_id: int) -> List[dict]:
    """Every category with its effective setting, created on demand."""
    existing = {
        p.category: p
        for p in db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id
            )
        ).scalars().all()
    }

    out = []
    for category in NotificationCategory:
        preference = existing.get(category)
        out.append(
            {
                "category": category,
                "in_app_enabled": preference.in_app_enabled if preference else True,
                "email_enabled": preference.email_enabled if preference else True,
                "sms_enabled": preference.sms_enabled if preference else False,
            }
        )
    return out


def purge_expired(db: Session) -> int:
    rows = (
        db.execute(
            select(Notification).where(
                Notification.expires_at.isnot(None),
                Notification.expires_at < utcnow(),
                Notification.is_read.is_(True),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)
