"""Attrition analytics response shapes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TrendPoint(BaseModel):
    period: str
    headcount: int
    joiners: int
    exits: int
    attrition_rate: float


class AttritionOverview(BaseModel):
    active_headcount: int
    exits_in_window: int
    voluntary_exits: int
    involuntary_exits: int
    attrition_rate_percent: float
    voluntary_rate_percent: float
    employees_at_high_risk: int
    window_months: int
    trend: List[TrendPoint] = []


class DepartmentAttrition(BaseModel):
    department_id: int
    department_name: str
    headcount: int
    exits: int
    attrition_rate_percent: float
    at_risk_count: int


class TenureAttrition(BaseModel):
    tenure_band: str
    employees: int
    exits: int
    attrition_rate_percent: float


class ExitReason(BaseModel):
    reason: str
    count: int
    percent: float


class ModelDrivers(BaseModel):
    model: Optional[Dict[str, Any]] = None
    drivers: List[Dict[str, Any]] = []
    note: str


class RiskDistribution(BaseModel):
    distribution: Dict[str, int] = {}
    unscored: int
    total_scored: int


class CohortRetention(BaseModel):
    cohort: str
    joined: int
    retained: int
    retention_percent: float
