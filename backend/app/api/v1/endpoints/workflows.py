"""Workflow and task management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.core.pagination import Page, PaginationParams, paginate
from app.models.enums import Priority, TaskStatus, WorkflowStatus
from app.models.user import User
from app.models.workflow import Task, TaskComment, Workflow
from app.schemas.common import MessageResponse
from app.schemas.workflow import (
    TaskCommentCreate,
    TaskCommentRead,
    TaskCreate,
    TaskRead,
    TaskStatistics,
    TaskUpdate,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowRead,
    WorkflowStart,
)
from app.services import workflow_service

router = APIRouter(tags=["Workflow & Tasks"])


# ------------------------------------------------------------------ workflows
@router.get("/workflows", response_model=Page[WorkflowRead], summary="List workflows")
def list_workflows(
    params: PaginationParams = Depends(),
    status_filter: Optional[WorkflowStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("workflow:manage")),
    db: Session = Depends(get_db),
):
    stmt = select(Workflow).where(Workflow.is_deleted.is_(False))
    if status_filter:
        stmt = stmt.where(Workflow.status == status_filter)
    stmt = stmt.order_by(Workflow.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[WorkflowRead].create(
        [WorkflowRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/workflows",
    response_model=WorkflowDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workflow with steps",
)
def create_workflow(
    payload: WorkflowCreate,
    current_user: User = Depends(RequirePermissions("workflow:manage")),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    data["steps"] = [dict(step) for step in data.get("steps", [])]
    return workflow_service.create_workflow(db, data, actor_id=current_user.id)


@router.get(
    "/workflows/{workflow_id}", response_model=WorkflowDetail, summary="Get a workflow"
)
def get_workflow(
    workflow_id: int,
    _: User = Depends(RequirePermissions("workflow:manage")),
    db: Session = Depends(get_db),
):
    return workflow_service.get_workflow(db, workflow_id)


@router.post(
    "/workflows/{workflow_id}/start",
    response_model=List[TaskRead],
    summary="Instantiate tasks for an employee",
)
def start_workflow(
    workflow_id: int,
    payload: WorkflowStart,
    current_user: User = Depends(RequirePermissions("workflow:manage")),
    db: Session = Depends(get_db),
):
    """
    One task per step. A step's `sla_days` becomes the due date counted from
    today, so a template started months later still gives the same window.
    """
    return workflow_service.start_workflow(
        db, workflow_id, payload.employee_id, actor_id=current_user.id
    )


# ---------------------------------------------------------------------- tasks
@router.get("/tasks", response_model=Page[TaskRead], summary="List tasks (scoped)")
def list_tasks(
    params: PaginationParams = Depends(),
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    priority: Optional[Priority] = Query(None),
    assigned_to_me: bool = Query(False),
    workflow_id: Optional[int] = Query(None),
    current_user: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Task).where(Task.is_deleted.is_(False))

    role = (current_user.role_name or "").lower()
    if role not in {"admin", "hr"} or assigned_to_me:
        stmt = stmt.where(
            or_(
                Task.assigned_to_id == current_user.id,
                Task.assigned_by_id == current_user.id,
            )
        )
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if workflow_id is not None:
        stmt = stmt.where(Task.workflow_id == workflow_id)

    stmt = stmt.order_by(Task.due_date.asc().nullslast(), Task.id.desc())
    rows, total = paginate(db, stmt, params)
    return Page[TaskRead].create(
        [TaskRead.model_validate(r) for r in rows], total, params
    )


@router.get("/tasks/overdue", response_model=List[TaskRead], summary="Overdue tasks")
def overdue(
    current_user: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    return workflow_service.overdue_tasks(db, current_user)


@router.get(
    "/tasks/statistics", response_model=TaskStatistics, summary="Task counts"
)
def statistics(
    current_user: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    return workflow_service.task_statistics(db, current_user)


@router.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
def create_task(
    payload: TaskCreate,
    current_user: User = Depends(RequirePermissions("task:manage")),
    db: Session = Depends(get_db),
):
    return workflow_service.create_task(
        db, payload.model_dump(exclude_none=True), actor_id=current_user.id
    )


@router.get("/tasks/{task_id}", response_model=TaskRead, summary="Get a task")
def get_task(
    task_id: int,
    _: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    return workflow_service.get_task(db, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskRead, summary="Update a task")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    """Completing a task requires its subtasks to be closed first."""
    return workflow_service.update_task(
        db, task_id, payload.model_dump(exclude_unset=True), current_user
    )


@router.post(
    "/tasks/{task_id}/comments",
    response_model=TaskCommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a task",
)
def add_comment(
    task_id: int,
    payload: TaskCommentCreate,
    current_user: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    return workflow_service.add_comment(
        db, task_id, current_user.id, payload.content
    )


@router.get(
    "/tasks/{task_id}/comments",
    response_model=List[TaskCommentRead],
    summary="Task discussion",
)
def list_comments(
    task_id: int,
    _: User = Depends(RequirePermissions("task:read")),
    db: Session = Depends(get_db),
):
    workflow_service.get_task(db, task_id)
    return (
        db.execute(
            select(TaskComment)
            .where(TaskComment.task_id == task_id)
            .order_by(TaskComment.id)
        )
        .scalars()
        .all()
    )
