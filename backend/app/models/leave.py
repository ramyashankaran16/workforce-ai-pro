"""Leave types, balances and requests."""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LeaveDuration, LeaveStatus, enum_col
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class LeaveType(Base, TimestampMixin, SoftDeleteMixin):
    """Configurable leave category, e.g. Casual, Sick, Earned."""

    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    annual_quota: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_consecutive_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_notice_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_carry_forward: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_carry_forward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    requires_document: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applicable_gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    color_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    balances: Mapped[List["LeaveBalance"]] = relationship(
        back_populates="leave_type", cascade="all, delete-orphan"
    )
    requests: Mapped[List["LeaveRequest"]] = relationship(back_populates="leave_type")

    def __repr__(self) -> str:
        return f"<LeaveType {self.code}>"


class LeaveBalance(Base, TimestampMixin):
    """Per-employee, per-type, per-year balance ledger."""

    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    allocated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    carried_forward: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pending: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    employee: Mapped["Employee"] = relationship(back_populates="leave_balances")
    leave_type: Mapped["LeaveType"] = relationship(back_populates="balances")

    @property
    def available(self) -> float:
        return (self.allocated + self.carried_forward) - (self.used + self.pending)

    def __repr__(self) -> str:
        return f"<LeaveBalance emp={self.employee_id} type={self.leave_type_id}>"


class LeaveRequest(Base, TimestampMixin):
    """An application for leave, moving through an approval flow."""

    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration: Mapped[LeaveDuration] = mapped_column(
        enum_col(LeaveDuration), default=LeaveDuration.FULL_DAY, nullable=False
    )
    total_days: Mapped[float] = mapped_column(Float, nullable=False)

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    contact_during_leave: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    attachment_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    status: Mapped[LeaveStatus] = mapped_column(
        enum_col(LeaveStatus), default=LeaveStatus.PENDING, nullable=False, index=True
    )
    approver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approver_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    employee: Mapped["Employee"] = relationship(
        back_populates="leave_requests", foreign_keys=[employee_id]
    )
    approver: Mapped[Optional["Employee"]] = relationship(foreign_keys=[approver_id])
    leave_type: Mapped["LeaveType"] = relationship(back_populates="requests")

    def __repr__(self) -> str:
        return f"<LeaveRequest emp={self.employee_id} {self.start_date}->{self.end_date}>"
