"""Audit trail, activity feed and login history."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AuditAction, enum_col
from app.models.mixins import TimestampMixin
from app.models.types import JSONType
from app.utils.date_utils import utcnow


class AuditLog(Base):
    """
    Immutable record of every mutating action.

    Written by middleware, never updated or deleted.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    action: Mapped[AuditAction] = mapped_column(
        enum_col(AuditAction), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    old_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    new_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    changed_fields: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    http_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    is_successful: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}#{self.entity_id}>"


class ActivityLog(Base):
    """Human-readable activity feed shown on dashboards."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    activity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    module: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    reference_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<ActivityLog {self.activity_type}>"


class LoginHistory(Base):
    """Successful and failed authentication attempts."""

    __tablename__ = "login_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email_attempted: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_successful: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    logged_in_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    logged_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    session_duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<LoginHistory {self.email_attempted} ok={self.is_successful}>"
