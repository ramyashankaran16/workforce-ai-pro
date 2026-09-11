"""Employee schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import (
    EmployeeEventType,
    EmployeeStatus,
    EmploymentType,
    Gender,
    MaritalStatus,
    WorkMode,
)
from app.schemas.common import ORMBase


class EmployeeBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: Optional[str] = Field(None, max_length=80)
    work_email: EmailStr
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    marital_status: Optional[MaritalStatus] = None

    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=80)
    state: Optional[str] = Field(None, max_length=80)
    country: Optional[str] = Field(None, max_length=80)
    postal_code: Optional[str] = Field(None, max_length=20)
    emergency_contact_name: Optional[str] = Field(None, max_length=120)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)

    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    manager_id: Optional[int] = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    work_mode: WorkMode = WorkMode.ONSITE
    work_location: Optional[str] = Field(None, max_length=150)
    notice_period_days: int = Field(30, ge=0, le=365)

    @field_validator("date_of_birth")
    @classmethod
    def dob_must_be_past(cls, v: Optional[date]) -> Optional[date]:
        if v and v >= date.today():
            raise ValueError("Date of birth must be in the past.")
        return v


class EmployeeCreate(EmployeeBase):
    employee_code: Optional[str] = Field(
        None, max_length=30, description="Auto-generated when omitted."
    )
    date_of_joining: date
    current_salary: Optional[float] = Field(None, ge=0)

    # optional login account
    create_user_account: bool = Field(
        False, description="Also create a User so this person can sign in."
    )
    user_role: str = Field("employee", description="Role for the created account.")
    user_password: Optional[str] = Field(
        None, description="Omit to generate a temporary password."
    )

    @field_validator("date_of_joining")
    @classmethod
    def joining_not_far_future(cls, v: date) -> date:
        if (v - date.today()).days > 365:
            raise ValueError("Date of joining cannot be more than a year ahead.")
        return v


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(None, max_length=80)
    work_email: Optional[EmailStr] = None
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    marital_status: Optional[MaritalStatus] = None

    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=80)
    state: Optional[str] = Field(None, max_length=80)
    country: Optional[str] = Field(None, max_length=80)
    postal_code: Optional[str] = Field(None, max_length=20)
    emergency_contact_name: Optional[str] = Field(None, max_length=120)
    emergency_contact_phone: Optional[str] = Field(None, max_length=20)

    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    manager_id: Optional[int] = None
    employment_type: Optional[EmploymentType] = None
    work_mode: Optional[WorkMode] = None
    work_location: Optional[str] = Field(None, max_length=150)
    notice_period_days: Optional[int] = Field(None, ge=0, le=365)

    status: Optional[EmployeeStatus] = None
    confirmation_date: Optional[date] = None
    current_salary: Optional[float] = Field(None, ge=0)
    last_promotion_date: Optional[date] = None

    # attrition-model attributes
    total_experience_years: Optional[float] = Field(None, ge=0, le=60)
    education_level: Optional[str] = Field(None, max_length=80)
    distance_from_home_km: Optional[float] = Field(None, ge=0)
    num_companies_worked: Optional[int] = Field(None, ge=0)
    training_hours_last_year: Optional[float] = Field(None, ge=0)
    business_travel_frequency: Optional[str] = Field(None, max_length=50)
    overtime_flag: Optional[bool] = None
    job_satisfaction_score: Optional[float] = Field(None, ge=1, le=5)
    work_life_balance_score: Optional[float] = Field(None, ge=1, le=5)
    environment_satisfaction_score: Optional[float] = Field(None, ge=1, le=5)
    last_performance_rating: Optional[float] = Field(None, ge=1, le=5)

    bio: Optional[str] = None
    profile_image: Optional[str] = Field(None, max_length=500)


class EmployeeExit(BaseModel):
    """Recording a departure."""

    date_of_exit: date
    status: EmployeeStatus = EmployeeStatus.RESIGNED
    exit_reason: str = Field(..., min_length=3)
    deactivate_user: bool = True

    @field_validator("status")
    @classmethod
    def must_be_exit_status(cls, v: EmployeeStatus) -> EmployeeStatus:
        allowed = {
            EmployeeStatus.RESIGNED,
            EmployeeStatus.TERMINATED,
            EmployeeStatus.RETIRED,
        }
        if v not in allowed:
            raise ValueError(
                "Exit status must be resigned, terminated or retired."
            )
        return v


class EmployeeRead(ORMBase):
    id: int
    employee_code: str
    first_name: str
    last_name: Optional[str] = None
    full_name: str
    work_email: EmailStr
    phone: Optional[str] = None
    department_id: Optional[int] = None
    designation_id: Optional[int] = None
    manager_id: Optional[int] = None
    employment_type: EmploymentType
    work_mode: WorkMode
    status: EmployeeStatus
    date_of_joining: date
    date_of_exit: Optional[date] = None
    profile_image: Optional[str] = None
    user_id: Optional[int] = None


class EmployeeDetail(EmployeeRead):
    personal_email: Optional[EmailStr] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    marital_status: Optional[MaritalStatus] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    confirmation_date: Optional[date] = None
    exit_reason: Optional[str] = None
    notice_period_days: int
    work_location: Optional[str] = None
    current_salary: Optional[float] = None
    last_hike_percent: Optional[float] = None
    last_promotion_date: Optional[date] = None

    total_experience_years: Optional[float] = None
    education_level: Optional[str] = None
    distance_from_home_km: Optional[float] = None
    num_companies_worked: Optional[int] = None
    training_hours_last_year: Optional[float] = None
    business_travel_frequency: Optional[str] = None
    overtime_flag: bool = False
    job_satisfaction_score: Optional[float] = None
    work_life_balance_score: Optional[float] = None
    environment_satisfaction_score: Optional[float] = None
    last_performance_rating: Optional[float] = None

    bio: Optional[str] = None
    tenure_months: Optional[int] = None

    # resolved labels, filled by the service
    department_name: Optional[str] = None
    designation_title: Optional[str] = None
    manager_name: Optional[str] = None
    reportee_count: int = 0


class EmployeeCreatedResponse(BaseModel):
    employee: EmployeeRead
    user_created: bool = False
    temporary_password: Optional[str] = None


class EmployeeHistoryRead(ORMBase):
    id: int
    event_type: EmployeeEventType
    effective_date: date
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime


class TeamMember(ORMBase):
    id: int
    employee_code: str
    full_name: str
    work_email: EmailStr
    designation_id: Optional[int] = None
    status: EmployeeStatus
    reportee_count: int = 0


class OrgNode(BaseModel):
    """Reporting tree node."""

    id: int
    employee_code: str
    full_name: str
    designation_title: Optional[str] = None
    department_name: Optional[str] = None
    reportees: List["OrgNode"] = []


OrgNode.model_rebuild()


class BulkImportRow(BaseModel):
    row_number: int
    employee_code: Optional[str] = None
    work_email: Optional[str] = None
    error: Optional[str] = None


class BulkImportResult(BaseModel):
    total_rows: int
    created: int
    skipped: int
    failures: List[BulkImportRow] = []
