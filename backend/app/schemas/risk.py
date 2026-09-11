"""Risk score, factor and alert schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import AlertStatus, Priority, RiskLevel, RiskTrend
from app.schemas.common import ORMBase


class RiskFactorRead(ORMBase):
    id: int
    factor_name: str
    factor_category: Optional[str] = None
    contribution: float
    current_value: Optional[str] = None
    is_negative: bool
    description: Optional[str] = None


class RiskScoreRead(ORMBase):
    id: int
    employee_id: int
    evaluation_date: date
    overall_score: float
    risk_level: RiskLevel
    trend: RiskTrend
    previous_score: Optional[float] = None
    score_change: Optional[float] = None
    summary: Optional[str] = None


class RiskScoreDetail(RiskScoreRead):
    ml_probability_score: Optional[float] = None
    attendance_score: Optional[float] = None
    leave_pattern_score: Optional[float] = None
    workload_score: Optional[float] = None
    performance_score: Optional[float] = None
    compensation_score: Optional[float] = None
    tenure_score: Optional[float] = None
    engagement_score: Optional[float] = None
    breakdown: Optional[Dict[str, Any]] = None
    factors: List[RiskFactorRead] = []
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None


class EvaluateResult(BaseModel):
    evaluated: int
    critical: int
    high: int
    medium: int
    low: int


class RiskAlertRead(ORMBase):
    id: int
    employee_id: int
    risk_score_id: Optional[int] = None
    alert_rule_id: Optional[int] = None
    title: str
    message: str
    risk_level: RiskLevel
    priority: Priority
    status: AlertStatus
    assigned_to_id: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime


class AlertResolve(BaseModel):
    notes: str = Field(..., min_length=3)
    dismiss: bool = Field(
        False, description="Dismiss rather than resolve, when no action was needed."
    )


class HeatmapEntry(BaseModel):
    department_id: int
    department_name: str
    headcount: int
    average_risk_score: float
    high_risk_count: int
    high_risk_percent: float
    distribution: Dict[str, int] = {}
