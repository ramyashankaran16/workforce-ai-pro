"""Intervention plan and action schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    InterventionOutcome,
    InterventionStatus,
    InterventionType,
    Priority,
)
from app.schemas.common import ORMBase


class InterventionCreate(BaseModel):
    employee_id: int
    title: str = Field(..., min_length=3, max_length=200)
    objective: Optional[str] = None
    intervention_type: InterventionType = InterventionType.OTHER
    priority: Priority = Priority.MEDIUM
    start_date: date
    target_end_date: Optional[date] = None
    estimated_cost: Optional[float] = Field(None, ge=0)
    risk_alert_id: Optional[int] = None
    owner_id: Optional[int] = None


class InterventionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    objective: Optional[str] = None
    intervention_type: Optional[InterventionType] = None
    priority: Optional[Priority] = None
    status: Optional[InterventionStatus] = None
    outcome: Optional[InterventionOutcome] = None
    outcome_notes: Optional[str] = None
    actual_cost: Optional[float] = Field(None, ge=0)
    target_end_date: Optional[date] = None
    owner_id: Optional[int] = None


class ActionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    due_date: Optional[date] = None


class ActionComplete(BaseModel):
    notes: Optional[str] = None


class ActionRead(ORMBase):
    id: int
    plan_id: int
    title: str
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    due_date: Optional[date] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    sequence: int
    notes: Optional[str] = None


class InterventionRead(ORMBase):
    id: int
    employee_id: int
    risk_alert_id: Optional[int] = None
    title: str
    objective: Optional[str] = None
    intervention_type: InterventionType
    priority: Priority
    status: InterventionStatus
    outcome: InterventionOutcome
    outcome_notes: Optional[str] = None
    risk_score_before: Optional[float] = None
    risk_score_after: Optional[float] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    start_date: date
    target_end_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    owner_id: Optional[int] = None


class InterventionDetail(InterventionRead):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    actions: List[ActionRead] = []


class EffectivenessReport(BaseModel):
    completed_plans: int
    improved_count: Optional[int] = None
    improved_percent: Optional[float] = None
    average_score_change: Optional[float] = None
    by_type: List[Dict[str, Any]] = []
    caveat: str
