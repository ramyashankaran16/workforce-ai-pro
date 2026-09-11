"""Notification schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    Priority,
)
from app.schemas.common import ORMBase


class NotificationRead(ORMBase):
    id: int
    title: str
    message: str
    notification_type: NotificationType
    category: NotificationCategory
    priority: Priority
    channel: NotificationChannel
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    action_url: Optional[str] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int
    by_priority: Dict[str, int] = {}


class PreferenceEntry(BaseModel):
    category: NotificationCategory
    in_app_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False


class PreferenceUpdate(BaseModel):
    preferences: List[PreferenceEntry] = Field(..., min_length=1)


class BroadcastRequest(BaseModel):
    """Send an announcement to whole roles."""

    roles: List[str] = Field(..., min_length=1, description="admin | hr | manager | employee")
    title: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=3)
    priority: Priority = Priority.MEDIUM
    category: NotificationCategory = NotificationCategory.SYSTEM
