"""Workforce stability index: periodic organisational health snapshots."""

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import RiskTrend, StabilityGrade, TargetScope, enum_col
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class StabilitySnapshot(Base, TimestampMixin):
    """
    A point-in-time stability reading for the org or one department.
    Drives the Workforce Stability Engine dashboard.
    """

    __tablename__ = "stability_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "scope", "department_id", name="uq_stability_snapshot"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scope: Mapped[TargetScope] = mapped_column(
        enum_col(TargetScope), default=TargetScope.ORGANISATION, nullable=False
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )

    stability_index: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    grade: Mapped[StabilityGrade] = mapped_column(
        enum_col(StabilityGrade), default=StabilityGrade.MODERATE, nullable=False, index=True
    )
    trend: Mapped[RiskTrend] = mapped_column(
        enum_col(RiskTrend), default=RiskTrend.STABLE, nullable=False
    )
    previous_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    total_headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joiners_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attrition_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    voluntary_attrition_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_tenure_months: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    high_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_risk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    average_satisfaction: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    absence_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overtime_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    commentary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metrics: Mapped[List["StabilityMetric"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<StabilitySnapshot {self.snapshot_date} {self.stability_index:.1f}>"


class StabilityMetric(Base):
    """An individual weighted metric feeding the stability index."""

    __tablename__ = "stability_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("stability_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    normalised_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    benchmark: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    snapshot: Mapped["StabilitySnapshot"] = relationship(back_populates="metrics")

    def __repr__(self) -> str:
        return f"<StabilityMetric {self.metric_name}={self.value}>"
