"""Workflow and task schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Priority, TaskStatus, WorkflowStatus
from app.schemas.common import ORMBase


class WorkflowStepCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    assignee_role: Optional[str] = Field(
        None, description="admin | hr | manager | employee"
    )
    assignee_user_id: Optional[int] = None
    sla_days: Optional[int] = Field(None, ge=1, le=365)
    is_mandatory: bool = True
    requires_approval: bool = False


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=60)
    trigger_event: Optional[str] = Field(None, max_length=80)
    is_template: bool = True
    steps: List[WorkflowStepCreate] = Field(default_factory=list)


class WorkflowStepRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    sequence: int
    assignee_role: Optional[str] = None
    assignee_user_id: Optional[int] = None
    sla_days: Optional[int] = None
    is_mandatory: bool
    requires_approval: bool


class WorkflowRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    status: WorkflowStatus
    is_template: bool
    trigger_event: Optional[str] = None


class WorkflowDetail(WorkflowRead):
    steps: List[WorkflowStepRead] = []


class WorkflowStart(BaseModel):
    employee_id: int


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    related_employee_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    priority: Priority = Priority.MEDIUM
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimated_hours: Optional[float] = Field(None, ge=0, le=1000)
    tags: Optional[Dict[str, Any]] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    assigned_to_id: Optional[int] = None
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    due_date: Optional[date] = None
    actual_hours: Optional[float] = Field(None, ge=0, le=1000)


class TaskRead(ORMBase):
    id: int
    reference: str
    title: str
    description: Optional[str] = None
    workflow_id: Optional[int] = None
    step_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    assigned_by_id: Optional[int] = None
    related_employee_id: Optional[int] = None
    status: TaskStatus
    priority: Priority
    progress_percent: int
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    created_at: datetime


class TaskCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=3000)


class TaskCommentRead(ORMBase):
    id: int
    task_id: int
    user_id: Optional[int] = None
    content: str
    created_at: datetime


class TaskStatistics(BaseModel):
    by_status: Dict[str, int] = {}
    total: int
    overdue: int
