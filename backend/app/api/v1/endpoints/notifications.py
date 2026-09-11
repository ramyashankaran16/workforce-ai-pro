"""Notification endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.core.pagination import Page, PaginationParams, paginate
from app.models.enums import NotificationCategory, Priority
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.notification import (
    BroadcastRequest,
    NotificationRead,
    PreferenceEntry,
    PreferenceUpdate,
    UnreadCount,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=Page[NotificationRead], summary="Own notifications")
def list_notifications(
    params: PaginationParams = Depends(),
    unread_only: bool = Query(False),
    category: Optional[NotificationCategory] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    if category:
        stmt = stmt.where(Notification.category == category)

    # unread first, then newest
    stmt = stmt.order_by(Notification.is_read, Notification.created_at.desc())
    rows, total = paginate(db, stmt, params)
    return Page[NotificationRead].create(
        [NotificationRead.model_validate(r) for r in rows], total, params
    )


@router.get("/count", response_model=UnreadCount, summary="Unread badge count")
def count(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return notification_service.unread_count(db, current_user.id)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one as read",
)
def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return notification_service.mark_read(db, notification_id, current_user.id)


@router.post("/read-all", response_model=MessageResponse, summary="Mark all as read")
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    count = notification_service.mark_all_read(db, current_user.id)
    return MessageResponse(message=f"Marked {count} notification(s) as read.")


@router.get(
    "/preferences",
    response_model=List[PreferenceEntry],
    summary="Per-category channel settings",
)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every category is returned, with defaults where nothing has been set."""
    return notification_service.list_preferences(db, current_user.id)


@router.put(
    "/preferences",
    response_model=List[PreferenceEntry],
    summary="Update channel settings",
)
def update_preferences(
    payload: PreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification_service.set_preferences(
        db, current_user.id, [p.model_dump() for p in payload.preferences]
    )
    return notification_service.list_preferences(db, current_user.id)


@router.post(
    "/broadcast",
    response_model=MessageResponse,
    summary="Send an announcement to whole roles",
)
def broadcast(
    payload: BroadcastRequest,
    _: User = Depends(RequirePermissions("system:manage")),
    db: Session = Depends(get_db),
):
    """Recipients who have muted that category in-app are skipped."""
    sent = notification_service.notify_roles(
        db,
        payload.roles,
        title=payload.title,
        message=payload.message,
        category=payload.category,
        priority=payload.priority,
    )
    return MessageResponse(message=f"Delivered to {sent} user(s).")
