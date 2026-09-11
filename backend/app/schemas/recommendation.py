"""Recommendation schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    Priority,
    RecommendationCategory,
    RecommendationStatus,
    TargetScope,
)
from app.schemas.common import ORMBase


class RecommendationRead(ORMBase):
    id: int
    title: str
    description: str
    rationale: Optional[str] = None
    category: RecommendationCategory
    scope: TargetScope
    employee_id: Optional[int] = None
    department_id: Optional[int] = None
    priority: Priority
    confidence: Optional[float] = None
    expected_impact: Optional[str] = None
    estimated_cost: Optional[float] = None
    supporting_data: Optional[Dict[str, Any]] = None
    status: RecommendationStatus
    generated_by: str
    created_at: datetime


class StatusUpdate(BaseModel):
    status: RecommendationStatus


class FeedbackSubmit(BaseModel):
    is_helpful: bool
    rating: Optional[int] = Field(None, ge=1, le=5)
    comments: Optional[str] = None


class GenerationResult(BaseModel):
    employees_evaluated: int
    recommendations_created: int
    already_open: int
    rules_applied: int


class FeedbackSummary(BaseModel):
    by_category: List[Dict[str, Any]] = []
    feedback_received: int
    rated_helpful: int
    note: str
