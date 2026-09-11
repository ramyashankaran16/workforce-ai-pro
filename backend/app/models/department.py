"""Organisational structure: departments and designations."""

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class Department(Base, TimestampMixin, SoftDeleteMixin):
    """A business unit. Supports nesting via parent_id."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    # use_alter breaks the circular FK between departments and employees
    head_employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_department_head"),
        nullable=True,
    )

    location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    budget: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    headcount_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped[Optional["Department"]] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[List["Department"]] = relationship(back_populates="parent")
    head: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[head_employee_id], post_update=True
    )
    employees: Mapped[List["Employee"]] = relationship(
        back_populates="department", foreign_keys="Employee.department_id"
    )
    designations: Mapped[List["Designation"]] = relationship(back_populates="department")

    def __repr__(self) -> str:
        return f"<Department {self.code}>"


class Designation(Base, TimestampMixin, SoftDeleteMixin):
    """Job title / grade within a department."""

    __tablename__ = "designations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_salary: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    max_salary: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped[Optional["Department"]] = relationship(back_populates="designations")
    employees: Mapped[List["Employee"]] = relationship(back_populates="designation")

    def __repr__(self) -> str:
        return f"<Designation {self.title}>"
