"""Leave type, balance and request schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import LeaveDuration, LeaveStatus
from app.schemas.common import ORMBase


# ----------------------------------------------------------------- leave type
class LeaveTypeBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: Optional[str] = None
    annual_quota: float = Field(0, ge=0, le=365)
    max_consecutive_days: Optional[int] = Field(None, ge=1, le=365)
    min_notice_days: int = Field(0, ge=0, le=90)
    is_paid: bool = True
    is_carry_forward: bool = False
    max_carry_forward: float = Field(0, ge=0, le=365)
    requires_document: bool = False
    color_code: Optional[str] = Field(None, max_length=10)


class LeaveTypeCreate(LeaveTypeBase):
    code: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")


class LeaveTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=80)
    description: Optional[str] = None
    annual_quota: Optional[float] = Field(None, ge=0, le=365)
    max_consecutive_days: Optional[int] = Field(None, ge=1, le=365)
    min_notice_days: Optional[int] = Field(None, ge=0, le=90)
    is_paid: Optional[bool] = None
    is_carry_forward: Optional[bool] = None
    max_carry_forward: Optional[float] = Field(None, ge=0, le=365)
    requires_document: Optional[bool] = None
    color_code: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None


class LeaveTypeRead(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    annual_quota: float
    max_consecutive_days: Optional[int] = None
    min_notice_days: int
    is_paid: bool
    is_carry_forward: bool
    max_carry_forward: float
    requires_document: bool
    color_code: Optional[str] = None
    is_active: bool


# -------------------------------------------------------------------- balance
class LeaveBalanceRead(ORMBase):
    id: int
    employee_id: int
    leave_type_id: int
    year: int
    allocated: float
    carried_forward: float
    used: float
    pending: float
    available: float
    leave_type_code: Optional[str] = None
    leave_type_name: Optional[str] = None


class BalanceAllocation(BaseModel):
    """Allocate or adjust a balance directly."""

    employee_id: int
    leave_type_id: int
    year: int = Field(..., ge=2000, le=2100)
    allocated: float = Field(..., ge=0, le=365)
    carried_forward: float = Field(0, ge=0, le=365)


# -------------------------------------------------------------------- request
class LeaveApply(BaseModel):
    leave_type_id: int
    start_date: date
    end_date: date
    duration: LeaveDuration = LeaveDuration.FULL_DAY
    reason: str = Field(..., min_length=5)
    contact_during_leave: Optional[str] = Field(None, max_length=50)
    attachment_path: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot precede start_date.")
        if self.duration != LeaveDuration.FULL_DAY and self.start_date != self.end_date:
            raise ValueError("Half-day leave must start and end on the same date.")
        return self


class LeaveDecision(BaseModel):
    remarks: Optional[str] = None


class LeaveRequestRead(ORMBase):
    id: int
    employee_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    duration: LeaveDuration
    total_days: float
    reason: str
    status: LeaveStatus
    approver_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    approver_remarks: Optional[str] = None
    contact_during_leave: Optional[str] = None
    attachment_path: Optional[str] = None
    created_at: datetime


class LeaveRequestDetail(LeaveRequestRead):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    leave_type_code: Optional[str] = None
    leave_type_name: Optional[str] = None
    approver_name: Optional[str] = None


class CarryForwardResult(BaseModel):
    from_year: int
    to_year: int
    employees_processed: int
    balances_created: int
    total_days_carried: float
