"""Shift, shift assignment, attendance and holiday schemas."""

from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AttendanceStatus, RegularizationStatus, ShiftType
from app.schemas.common import ORMBase


# ---------------------------------------------------------------------- shift
class ShiftBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    shift_type: ShiftType = ShiftType.GENERAL
    start_time: time
    end_time: time
    break_minutes: int = Field(60, ge=0, le=240)
    grace_period_minutes: int = Field(15, ge=0, le=120)
    half_day_threshold_hours: float = Field(4.0, ge=0, le=12)
    description: Optional[str] = None


class ShiftCreate(ShiftBase):
    code: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")

    @model_validator(mode="after")
    def derive_night_and_hours(self):
        # end <= start means the shift rolls past midnight
        self._is_night = self.end_time <= self.start_time
        return self


class ShiftUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    shift_type: Optional[ShiftType] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: Optional[int] = Field(None, ge=0, le=240)
    grace_period_minutes: Optional[int] = Field(None, ge=0, le=120)
    half_day_threshold_hours: Optional[float] = Field(None, ge=0, le=12)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ShiftRead(ORMBase):
    id: int
    code: str
    name: str
    shift_type: ShiftType
    start_time: time
    end_time: time
    break_minutes: int
    working_hours: float
    grace_period_minutes: int
    half_day_threshold_hours: float
    is_night_shift: bool
    is_active: bool
    description: Optional[str] = None


# ----------------------------------------------------------- shift assignment
class ShiftAssignCreate(BaseModel):
    employee_ids: List[int] = Field(..., min_length=1)
    start_date: date
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def check_range(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date.")
        return self


class ShiftAssignmentRead(ORMBase):
    id: int
    employee_id: int
    shift_id: int
    start_date: date
    end_date: Optional[date] = None
    is_active: bool


class RosterEntry(BaseModel):
    employee_id: int
    employee_code: str
    full_name: str
    shift_code: Optional[str] = None
    shift_name: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None


# ----------------------------------------------------------------- attendance
class CheckInRequest(BaseModel):
    location: Optional[str] = Field(None, max_length=200)
    is_remote: bool = False


class CheckOutRequest(BaseModel):
    remarks: Optional[str] = None


class AttendanceRead(ORMBase):
    id: int
    employee_id: int
    shift_id: Optional[int] = None
    attendance_date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: AttendanceStatus
    worked_hours: float
    overtime_hours: float
    late_minutes: int
    early_exit_minutes: int
    is_remote: bool
    regularization_status: RegularizationStatus
    regularization_reason: Optional[str] = None
    remarks: Optional[str] = None


class AttendanceDetail(AttendanceRead):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    shift_code: Optional[str] = None


class AttendanceManualCreate(BaseModel):
    """HR entering or correcting a record directly."""

    employee_id: int
    attendance_date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    status: AttendanceStatus
    is_remote: bool = False
    remarks: Optional[str] = None


class RegularizationRequest(BaseModel):
    attendance_date: date
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    reason: str = Field(..., min_length=5)


class RegularizationDecision(BaseModel):
    approve: bool
    remarks: Optional[str] = None


class AttendanceSummary(BaseModel):
    employee_id: int
    employee_code: str
    full_name: str
    period_start: date
    period_end: date
    working_days: int
    present_days: float
    absent_days: float
    leave_days: float
    half_days: int
    late_count: int
    total_worked_hours: float
    total_overtime_hours: float
    attendance_percent: float


# -------------------------------------------------------------------- holiday
class HolidayCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    holiday_date: date
    is_optional: bool = False
    location: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None


class HolidayRead(ORMBase):
    id: int
    name: str
    holiday_date: date
    is_optional: bool
    location: Optional[str] = None
    description: Optional[str] = None
