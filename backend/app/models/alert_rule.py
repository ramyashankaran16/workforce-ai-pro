"""Configurable rules that drive the smart alert engine."""

from datetime import datetime
from typing import Any, Dict, List, Optional

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
from app.models.enums import (
    NotificationChannel,
    Priority,
    RuleOperator,
    RuleTargetMetric,
    TargetScope,
    enum_col,
)
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class AlertRule(Base, TimestampMixin):
    """
    A threshold rule, e.g. "attrition_probability >= 0.75 for the Sales
    department -> notify HR with high priority".
    """

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metric: Mapped[RuleTargetMetric] = mapped_column(
        enum_col(RuleTargetMetric), nullable=False, index=True
    )
    operator: Mapped[RuleOperator] = mapped_column(enum_col(RuleOperator), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    secondary_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    scope: Mapped[TargetScope] = mapped_column(
        enum_col(TargetScope), default=TargetScope.ORGANISATION, nullable=False
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True
    )
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=True
    )

    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_col(NotificationChannel), default=NotificationChannel.IN_APP, nullable=False
    )
    notify_roles: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    message_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    triggers: Mapped[List["AlertTrigger"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AlertRule {self.name} {self.metric} {self.operator} {self.threshold_value}>"


class AlertTrigger(Base, TimestampMixin):
    """An audit row recorded every time a rule fires."""

    __tablename__ = "alert_triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )

    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    notifications_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rule: Mapped["AlertRule"] = relationship(back_populates="triggers")

    def __repr__(self) -> str:
        return f"<AlertTrigger rule={self.rule_id} value={self.metric_value}>"
