"""In-app notifications and per-user delivery preferences."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    Priority,
    enum_col,
)
from app.models.mixins import TimestampMixin


class Notification(Base, TimestampMixin):
    """A message delivered to one user, in-app and optionally by email."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[NotificationType] = mapped_column(
        enum_col(NotificationType), default=NotificationType.INFO, nullable=False
    )
    category: Mapped[NotificationCategory] = mapped_column(
        enum_col(NotificationCategory),
        default=NotificationCategory.SYSTEM,
        nullable=False,
        index=True,
    )
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_col(NotificationChannel), default=NotificationChannel.IN_APP, nullable=False
    )

    # Generic pointer so a notification can link to any entity
    reference_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification user={self.user_id} {self.title[:24]}>"


class NotificationPreference(Base, TimestampMixin):
    """Per-user, per-category channel toggles."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[NotificationCategory] = mapped_column(
        enum_col(NotificationCategory), nullable=False
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<NotificationPreference user={self.user_id} {self.category}>"
