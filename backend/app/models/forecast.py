"""Workforce forecasting and what-if scenarios."""

from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ForecastGranularity, ForecastType, enum_col
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class WorkforceForecast(Base, TimestampMixin):
    """A projection of headcount, attrition or hiring need over time."""

    __tablename__ = "workforce_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    forecast_type: Mapped[ForecastType] = mapped_column(
        enum_col(ForecastType), default=ForecastType.ATTRITION_RATE, nullable=False, index=True
    )
    granularity: Mapped[ForecastGranularity] = mapped_column(
        enum_col(ForecastGranularity), default=ForecastGranularity.MONTHLY, nullable=False
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_periods: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    method: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    projected_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy_mape: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assumptions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    generated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    data_points: Mapped[List["ForecastDataPoint"]] = relationship(
        back_populates="forecast", cascade="all, delete-orphan"
    )
    scenarios: Mapped[List["ForecastScenario"]] = relationship(
        back_populates="forecast", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WorkforceForecast {self.name} {self.forecast_type}>"


class ForecastDataPoint(Base):
    """A single period on a forecast curve."""

    __tablename__ = "forecast_data_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("workforce_forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_label: Mapped[str] = mapped_column(String(40), nullable=False)
    period_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    actual_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_projection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    forecast: Mapped["WorkforceForecast"] = relationship(back_populates="data_points")

    def __repr__(self) -> str:
        return f"<ForecastDataPoint {self.period_label} {self.predicted_value}>"


class ForecastScenario(Base, TimestampMixin):
    """A what-if variant: adjust hiring, attrition or salary and re-project."""

    __tablename__ = "forecast_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("workforce_forecasts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    hiring_rate_change: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attrition_rate_change: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    salary_increase_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    projected_headcount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    projected_attrition_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    projected_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    forecast: Mapped["WorkforceForecast"] = relationship(back_populates="scenarios")

    def __repr__(self) -> str:
        return f"<ForecastScenario {self.name}>"
