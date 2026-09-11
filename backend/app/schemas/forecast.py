"""Forecast and scenario schemas."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import ForecastGranularity, ForecastType
from app.schemas.common import ORMBase


class ForecastCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    forecast_type: ForecastType = ForecastType.ATTRITION_RATE
    horizon_periods: int = Field(6, ge=1, le=24)
    lookback_periods: int = Field(12, ge=3, le=60)
    department_id: Optional[int] = None
    confidence: float = Field(0.90, ge=0.5, le=0.99)
    description: Optional[str] = None


class ForecastDataPointRead(ORMBase):
    id: int
    period_label: str
    period_date: date
    actual_value: Optional[float] = None
    predicted_value: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    is_projection: bool


class ForecastRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    forecast_type: ForecastType
    granularity: ForecastGranularity
    department_id: Optional[int] = None
    period_start: date
    period_end: date
    horizon_periods: int
    method: Optional[str] = None
    baseline_value: Optional[float] = None
    projected_value: Optional[float] = None
    confidence_level: Optional[float] = None
    assumptions: Optional[Dict[str, Any]] = None


class ForecastDetail(ForecastRead):
    data_points: List[ForecastDataPointRead] = []


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = None
    hiring_rate_change: float = Field(0.0, ge=-100, le=200)
    attrition_rate_change: float = Field(0.0, ge=-50, le=50)
    salary_increase_percent: float = Field(0.0, ge=0, le=50)
    parameters: Optional[Dict[str, Any]] = None
    is_baseline: bool = False


class ScenarioRead(ORMBase):
    id: int
    forecast_id: int
    name: str
    description: Optional[str] = None
    hiring_rate_change: float
    attrition_rate_change: float
    salary_increase_percent: float
    projected_headcount: Optional[float] = None
    projected_attrition_rate: Optional[float] = None
    results: Optional[Dict[str, Any]] = None
    is_baseline: bool
