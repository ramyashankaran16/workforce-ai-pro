"""Employee risk scoring, contributing factors and alerts."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
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
    AlertStatus,
    Priority,
    RiskLevel,
    RiskTrend,
    enum_col,
)
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class RiskScore(Base, TimestampMixin):
    """
    A composite score blending the ML probability with behavioural signals
    (attendance, leave, overtime, performance, tenure).
    """

    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prediction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("attrition_predictions.id", ondelete="SET NULL"), nullable=True
    )

    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_col(RiskLevel), default=RiskLevel.LOW, nullable=False, index=True
    )
    trend: Mapped[RiskTrend] = mapped_column(
        enum_col(RiskTrend), default=RiskTrend.STABLE, nullable=False
    )
    previous_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_change: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Sub-scores, each normalised to 0-100
    ml_probability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attendance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    leave_pattern_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    workload_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    performance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compensation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tenure_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    engagement_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="risk_scores")
    factors: Mapped[List["RiskFactor"]] = relationship(
        back_populates="risk_score", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RiskScore emp={self.employee_id} {self.overall_score:.1f} {self.risk_level}>"


class RiskFactor(Base):
    """One contributing driver behind a risk score."""

    __tablename__ = "risk_factors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_score_id: Mapped[int] = mapped_column(
        ForeignKey("risk_scores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    factor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    factor_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    current_value: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    benchmark_value: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_negative: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    risk_score: Mapped["RiskScore"] = relationship(back_populates="factors")

    def __repr__(self) -> str:
        return f"<RiskFactor {self.factor_name} {self.contribution:.2f}>"


class RiskAlert(Base, TimestampMixin):
    """A raised alert requiring HR or manager attention."""

    __tablename__ = "risk_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_score_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("risk_scores.id", ondelete="SET NULL"), nullable=True
    )
    alert_rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        enum_col(RiskLevel), default=RiskLevel.MEDIUM, nullable=False, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        enum_col(AlertStatus), default=AlertStatus.NEW, nullable=False, index=True
    )

    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    acknowledged_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(
        back_populates="risk_alerts", foreign_keys=[employee_id]
    )

    def __repr__(self) -> str:
        return f"<RiskAlert emp={self.employee_id} {self.status}>"
