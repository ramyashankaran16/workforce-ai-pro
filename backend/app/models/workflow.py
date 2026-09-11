"""Workflows, steps, tasks and task comments."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import Priority, TaskStatus, WorkflowStatus, enum_col
from app.models.mixins import SoftDeleteMixin, TimestampMixin
from app.models.types import JSONType


class Workflow(Base, TimestampMixin, SoftDeleteMixin):
    """A reusable multi-step process, e.g. onboarding or exit clearance."""

    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)

    status: Mapped[WorkflowStatus] = mapped_column(
        enum_col(WorkflowStatus), default=WorkflowStatus.DRAFT, nullable=False, index=True
    )
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trigger_event: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    configuration: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    steps: Mapped[List["WorkflowStep"]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.sequence",
    )
    tasks: Mapped[List["Task"]] = relationship(back_populates="workflow")

    def __repr__(self) -> str:
        return f"<Workflow {self.name}>"


class WorkflowStep(Base, TimestampMixin):
    """An ordered stage within a workflow."""

    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assignee_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assignee_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    sla_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    workflow: Mapped["Workflow"] = relationship(back_populates="steps")
    tasks: Mapped[List["Task"]] = relationship(back_populates="step")

    def __repr__(self) -> str:
        return f"<WorkflowStep {self.sequence}. {self.name}>"


class Task(Base, TimestampMixin, SoftDeleteMixin):
    """A unit of work assigned to a user."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    workflow_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True
    )
    parent_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )

    assigned_to_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    related_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[TaskStatus] = mapped_column(
        enum_col(TaskStatus), default=TaskStatus.TODO, nullable=False, index=True
    )
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority), default=Priority.MEDIUM, nullable=False, index=True
    )
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    workflow: Mapped[Optional["Workflow"]] = relationship(back_populates="tasks")
    step: Mapped[Optional["WorkflowStep"]] = relationship(back_populates="tasks")
    subtasks: Mapped[List["Task"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped[Optional["Task"]] = relationship(
        remote_side=[id], back_populates="subtasks"
    )
    comments: Mapped[List["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.status == TaskStatus.COMPLETED:
            return False
        return self.due_date < date.today()

    def __repr__(self) -> str:
        return f"<Task {self.reference} {self.status}>"


class TaskComment(Base, TimestampMixin):
    """A discussion note attached to a task."""

    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="comments")

    def __repr__(self) -> str:
        return f"<TaskComment task={self.task_id}>"
