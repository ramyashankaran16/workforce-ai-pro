"""Shifts, shift assignments and daily attendance."""

from datetime import date, datetime, time
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
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    AttendanceStatus,
    RegularizationStatus,
    ShiftType,
    enum_col,
)
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class Shift(Base, TimestampMixin, SoftDeleteMixin):
    """A working-hours template employees can be assigned to."""

    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    shift_type: Mapped[ShiftType] = mapped_column(
        enum_col(ShiftType), default=ShiftType.GENERAL, nullable=False
    )

    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    working_hours: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)

    grace_period_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    half_day_threshold_hours: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    assignments: Mapped[List["ShiftAssignment"]] = relationship(
        back_populates="shift", cascade="all, delete-orphan"
    )
    attendances: Mapped[List["Attendance"]] = relationship(back_populates="shift")

    def __repr__(self) -> str:
        return f"<Shift {self.code}>"


class ShiftAssignment(Base, TimestampMixin):
    """Assigns an employee to a shift for a date range."""

    __tablename__ = "shift_assignments"
    __table_args__ = (
        UniqueConstraint("employee_id", "shift_id", "start_date", name="uq_shift_assignment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    employee: Mapped["Employee"] = relationship(back_populates="shift_assignments")
    shift: Mapped["Shift"] = relationship(back_populates="assignments")

    def __repr__(self) -> str:
        return f"<ShiftAssignment emp={self.employee_id} shift={self.shift_id}>"


class Attendance(Base, TimestampMixin):
    """One row per employee per calendar day."""

    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="uq_employee_attendance_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    check_in: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    check_out: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    check_in_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    check_out_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    check_in_location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    status: Mapped[AttendanceStatus] = mapped_column(
        enum_col(AttendanceStatus),
        default=AttendanceStatus.ABSENT,
        nullable=False,
        index=True,
    )
    worked_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_exit_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    regularization_status: Mapped[RegularizationStatus] = mapped_column(
        enum_col(RegularizationStatus),
        default=RegularizationStatus.NOT_REQUESTED,
        nullable=False,
    )
    regularization_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(back_populates="attendances")
    shift: Mapped[Optional["Shift"]] = relationship(back_populates="attendances")

    def __repr__(self) -> str:
        return f"<Attendance emp={self.employee_id} {self.attendance_date} {self.status}>"


class Holiday(Base, TimestampMixin):
    """Company holiday calendar, used when marking attendance."""

    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("holiday_date", "name", name="uq_holiday"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Holiday {self.name} {self.holiday_date}>"
