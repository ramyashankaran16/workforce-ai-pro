"""Performance review, goal and feedback schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import GoalStatus, ReviewCycleStatus, ReviewStatus
from app.schemas.common import ORMBase


class ReviewCycleCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    description: Optional[str] = None
    period_start: date
    period_end: date
    self_review_deadline: Optional[date] = None
    manager_review_deadline: Optional[date] = None
    rating_scale_max: int = Field(5, ge=3, le=10)
    competencies: Optional[Dict[str, Any]] = None


class ReviewCycleRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    period_start: date
    period_end: date
    self_review_deadline: Optional[date] = None
    manager_review_deadline: Optional[date] = None
    status: ReviewCycleStatus
    rating_scale_max: int


class ReviewAdvance(BaseModel):
    """Submit the current stage and move to the next."""

    self_rating: Optional[float] = Field(None, ge=1, le=10)
    manager_rating: Optional[float] = Field(None, ge=1, le=10)
    final_rating: Optional[float] = Field(None, ge=1, le=10)
    competency_ratings: Optional[Dict[str, Any]] = None
    self_comments: Optional[str] = None
    manager_comments: Optional[str] = None
    hr_comments: Optional[str] = None
    strengths: Optional[str] = None
    improvement_areas: Optional[str] = None
    training_recommendations: Optional[str] = None
    promotion_recommended: Optional[bool] = None
    hike_recommended_percent: Optional[float] = Field(None, ge=0, le=100)


class PerformanceReviewRead(ORMBase):
    id: int
    cycle_id: int
    employee_id: int
    reviewer_id: Optional[int] = None
    status: ReviewStatus
    self_rating: Optional[float] = None
    manager_rating: Optional[float] = None
    final_rating: Optional[float] = None
    self_comments: Optional[str] = None
    manager_comments: Optional[str] = None
    hr_comments: Optional[str] = None
    strengths: Optional[str] = None
    improvement_areas: Optional[str] = None
    promotion_recommended: bool
    hike_recommended_percent: Optional[float] = None
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class GoalCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=60)
    metric: Optional[str] = Field(None, max_length=120)
    target_value: Optional[float] = None
    weight_percent: float = Field(0, ge=0, le=100)
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    review_id: Optional[int] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    achieved_value: Optional[float] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[GoalStatus] = None
    due_date: Optional[date] = None


class GoalRead(ORMBase):
    id: int
    employee_id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    metric: Optional[str] = None
    target_value: Optional[float] = None
    achieved_value: Optional[float] = None
    weight_percent: float
    status: GoalStatus
    progress_percent: int
    start_date: Optional[date] = None
    due_date: Optional[date] = None


class FeedbackCreate(BaseModel):
    to_employee_id: int
    content: str = Field(..., min_length=5)
    feedback_type: str = Field("peer", max_length=40)
    rating: Optional[float] = Field(None, ge=1, le=5)
    is_anonymous: bool = False
    is_visible_to_employee: bool = True
    review_id: Optional[int] = None


class FeedbackRead(ORMBase):
    id: int
    from_employee_id: Optional[int] = None
    to_employee_id: int
    feedback_type: str
    content: str
    rating: Optional[float] = None
    is_anonymous: bool
    created_at: datetime
