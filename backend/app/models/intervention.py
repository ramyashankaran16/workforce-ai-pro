"""HR intervention plans and their individual actions."""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    InterventionOutcome,
    InterventionStatus,
    InterventionType,
    Priority,
    enum_col,
)
from app.models.mixins import TimestampMixin


class InterventionPlan(Base, TimestampMixin):
    """A retention plan created for an at-risk employee."""

    __tablename__ = "intervention_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_alert_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("risk_alerts.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intervention_type: Mapped[InterventionType] = mapped_column(
        enum_col(InterventionType), default=InterventionType.OTHER, nullable=False, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False
    )
    status: Mapped[InterventionStatus] = mapped_column(
        enum_col(InterventionStatus),
        default=InterventionStatus.PLANNED,
        nullable=False,
        index=True,
    )

    risk_score_before: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_score_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome: Mapped[InterventionOutcome] = mapped_column(
        enum_col(InterventionOutcome), default=InterventionOutcome.PENDING, nullable=False
    )
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    estimated_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    actual_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    employee: Mapped["Employee"] = relationship(
        back_populates="interventions", foreign_keys=[employee_id]
    )
    actions: Mapped[List["InterventionAction"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<InterventionPlan emp={self.employee_id} {self.intervention_type}>"


class InterventionAction(Base, TimestampMixin):
    """A concrete step inside an intervention plan."""

    __tablename__ = "intervention_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("intervention_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    plan: Mapped["InterventionPlan"] = relationship(back_populates="actions")

    def __repr__(self) -> str:
        return f"<InterventionAction {self.title[:24]}>"
