"""Workflow templates, instantiation and task lifecycle."""

import logging
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.models.employee import Employee
from app.models.enums import (
    NotificationCategory,
    Priority,
    TaskStatus,
    WorkflowStatus,
)
from app.models.role import Role
from app.models.user import User
from app.models.workflow import Task, TaskComment, Workflow, WorkflowStep
from app.services import notification_service
from app.utils.code_generator import generate_task_reference
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

OPEN_STATUSES = {TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW,
                 TaskStatus.BLOCKED}


def create_workflow(db: Session, data: dict, actor_id: Optional[int] = None) -> Workflow:
    steps = data.pop("steps", [])
    workflow = Workflow(**data, created_by_id=actor_id)
    db.add(workflow)
    db.flush()

    for index, step in enumerate(steps, start=1):
        db.add(WorkflowStep(workflow_id=workflow.id, sequence=index, **step))

    db.commit()
    db.refresh(workflow)
    return workflow


def get_workflow(db: Session, workflow_id: int) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None or workflow.is_deleted:
        raise NotFoundError("Workflow not found.")
    return workflow


def _resolve_assignee(db: Session, step: WorkflowStep, employee: Employee) -> Optional[int]:
    """Explicit user wins; otherwise the first holder of the named role."""
    if step.assignee_user_id:
        return step.assignee_user_id
    if step.assignee_role:
        if step.assignee_role.lower() == "manager" and employee.manager_id:
            manager = db.get(Employee, employee.manager_id)
            if manager and manager.user_id:
                return manager.user_id
        user = db.execute(
            select(User)
            .join(Role)
            .where(Role.name == step.assignee_role.lower(), User.is_deleted.is_(False))
        ).scalars().first()
        return user.id if user else None
    return None


def start_workflow(
    db: Session, workflow_id: int, employee_id: int, actor_id: Optional[int] = None
) -> List[Task]:
    """
    Instantiate one task per step for an employee.

    SLA days on a step become the task's due date, counted forward from today
    rather than from the workflow's creation, so a template started six months
    later still gives people the same window.
    """
    workflow = get_workflow(db, workflow_id)
    if workflow.status not in {WorkflowStatus.ACTIVE, WorkflowStatus.DRAFT}:
        raise BusinessRuleError(f"Workflow is {workflow.status.value}.")

    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    steps = sorted(workflow.steps, key=lambda s: s.sequence)
    if not steps:
        raise BusinessRuleError("This workflow has no steps to instantiate.")

    created = []
    for step in steps:
        assignee_id = _resolve_assignee(db, step, employee)
        task = Task(
            reference=generate_task_reference(db),
            title=f"{step.name} — {employee.full_name}",
            description=step.description,
            workflow_id=workflow.id,
            step_id=step.id,
            assigned_to_id=assignee_id,
            assigned_by_id=actor_id,
            related_employee_id=employee.id,
            status=TaskStatus.TODO,
            priority=Priority.HIGH if step.is_mandatory else Priority.MEDIUM,
            start_date=date.today(),
            due_date=(
                date.today() + timedelta(days=step.sla_days) if step.sla_days else None
            ),
        )
        db.add(task)
        db.flush()
        created.append(task)

        if assignee_id:
            notification_service.notify(
                db,
                assignee_id,
                title="Task assigned",
                message=f"{task.title} (due {task.due_date or 'no date set'})",
                category=NotificationCategory.TASK,
                reference_type="task",
                reference_id=task.id,
                action_url=f"/tasks/{task.id}",
                commit=False,
            )

    if workflow.status == WorkflowStatus.DRAFT:
        workflow.status = WorkflowStatus.ACTIVE

    db.commit()
    for task in created:
        db.refresh(task)
    return created


def create_task(db: Session, data: dict, actor_id: Optional[int] = None) -> Task:
    if data.get("due_date") and data.get("start_date"):
        if data["due_date"] < data["start_date"]:
            raise BusinessRuleError("The due date cannot precede the start date.")

    task = Task(
        reference=generate_task_reference(db), assigned_by_id=actor_id, **data
    )
    db.add(task)
    db.flush()

    if task.assigned_to_id:
        notification_service.notify(
            db,
            task.assigned_to_id,
            title="Task assigned",
            message=f"{task.title} (due {task.due_date or 'no date set'})",
            category=NotificationCategory.TASK,
            reference_type="task",
            reference_id=task.id,
            commit=False,
        )

    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.is_deleted:
        raise NotFoundError("Task not found.")
    return task


def update_task(db: Session, task_id: int, data: dict, user: User) -> Task:
    task = get_task(db, task_id)

    role = (user.role_name or "").lower()
    if role not in {"admin", "hr"} and task.assigned_to_id != user.id:
        if task.assigned_by_id != user.id:
            raise PermissionDeniedError(
                "You can only update tasks assigned to or by you."
            )

    new_status = data.get("status")
    if new_status == TaskStatus.COMPLETED:
        open_subtasks = db.execute(
            select(func.count(Task.id)).where(
                Task.parent_task_id == task.id,
                Task.status.in_(list(OPEN_STATUSES)),
                Task.is_deleted.is_(False),
            )
        ).scalar() or 0
        if open_subtasks:
            raise BusinessRuleError(f"{open_subtasks} subtask(s) are still open.")

        data.setdefault("progress_percent", 100)
        task.completed_at = utcnow()

        if task.assigned_by_id and task.assigned_by_id != user.id:
            notification_service.notify(
                db,
                task.assigned_by_id,
                title="Task completed",
                message=f"{task.title} was completed by {user.full_name}.",
                category=NotificationCategory.TASK,
                reference_type="task",
                reference_id=task.id,
                commit=False,
            )

    for field, value in data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    return task


def add_comment(db: Session, task_id: int, user_id: int, content: str) -> TaskComment:
    get_task(db, task_id)
    comment = TaskComment(task_id=task_id, user_id=user_id, content=content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def overdue_tasks(db: Session, user: Optional[User] = None) -> List[Task]:
    stmt = select(Task).where(
        Task.is_deleted.is_(False),
        Task.due_date.isnot(None),
        Task.due_date < date.today(),
        Task.status.in_(list(OPEN_STATUSES)),
    )
    if user is not None and (user.role_name or "").lower() not in {"admin", "hr"}:
        stmt = stmt.where(Task.assigned_to_id == user.id)
    return db.execute(stmt.order_by(Task.due_date)).scalars().all()


def task_statistics(db: Session, user: Optional[User] = None) -> dict:
    stmt = select(Task.status, func.count(Task.id)).where(Task.is_deleted.is_(False))
    if user is not None and (user.role_name or "").lower() not in {"admin", "hr"}:
        stmt = stmt.where(Task.assigned_to_id == user.id)

    rows = db.execute(stmt.group_by(Task.status)).all()
    counts = {
        str(status.value if hasattr(status, "value") else status): int(count)
        for status, count in rows
    }
    return {
        "by_status": counts,
        "total": sum(counts.values()),
        "overdue": len(overdue_tasks(db, user)),
    }
