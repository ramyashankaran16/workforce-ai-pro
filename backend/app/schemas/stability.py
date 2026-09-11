"""Workforce stability schemas."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models.enums import RiskTrend, StabilityGrade, TargetScope
from app.schemas.common import ORMBase


class StabilityMetricRead(ORMBase):
    id: int
    metric_name: str
    metric_category: Optional[str] = None
    value: float
    normalised_score: Optional[float] = None
    weight: float
    benchmark: Optional[float] = None
    unit: Optional[str] = None


class StabilitySnapshotRead(ORMBase):
    id: int
    snapshot_date: date
    scope: TargetScope
    department_id: Optional[int] = None
    stability_index: float
    grade: StabilityGrade
    trend: RiskTrend
    previous_index: Optional[float] = None
    total_headcount: int
    joiners_count: int
    exits_count: int
    attrition_rate: Optional[float] = None
    average_tenure_months: Optional[float] = None
    high_risk_count: int
    average_satisfaction: Optional[float] = None
    absence_rate: Optional[float] = None
    overtime_ratio: Optional[float] = None
    commentary: Optional[str] = None


class StabilityDetail(StabilitySnapshotRead):
    breakdown: Optional[Dict[str, Any]] = None
    metrics: List[StabilityMetricRead] = []


class DepartmentStability(BaseModel):
    department_id: int
    department_name: str
    stability_index: float
    grade: str
    trend: str
    headcount: int
    attrition_rate: Optional[float] = None
    high_risk_count: int
