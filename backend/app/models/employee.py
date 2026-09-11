"""Employee master record and its change history."""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    EmployeeEventType,
    EmployeeStatus,
    EmploymentType,
    Gender,
    MaritalStatus,
    WorkMode,
    enum_col,
)
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class Employee(Base, TimestampMixin, SoftDeleteMixin):
    """
    The HR profile. Deliberately wide because most attrition model features
    are derived from these columns.
    """

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True
    )

    # ---- personal
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    personal_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    work_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    gender: Mapped[Optional[Gender]] = mapped_column(enum_col(Gender), nullable=True)
    marital_status: Mapped[Optional[MaritalStatus]] = mapped_column(
        enum_col(MaritalStatus), nullable=True
    )
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # ---- employment
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    designation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("designations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        enum_col(EmploymentType), default=EmploymentType.FULL_TIME, nullable=False
    )
    work_mode: Mapped[WorkMode] = mapped_column(
        enum_col(WorkMode), default=WorkMode.ONSITE, nullable=False
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        enum_col(EmployeeStatus),
        default=EmployeeStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    confirmation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    work_location: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # ---- compensation snapshot (payroll holds the authoritative structure)
    current_salary: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    last_hike_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_hike_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_promotion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ---- attrition model features (refreshed by scheduled jobs)
    total_experience_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    education_level: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    distance_from_home_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_companies_worked: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    training_hours_last_year: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_travel_frequency: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    overtime_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    job_satisfaction_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    work_life_balance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    environment_satisfaction_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_performance_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ---- denormalised risk snapshot for fast dashboard queries
    current_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    current_risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    last_risk_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    profile_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="employee")
    department: Mapped[Optional["Department"]] = relationship(
        back_populates="employees", foreign_keys=[department_id]
    )
    designation: Mapped[Optional["Designation"]] = relationship(back_populates="employees")
    manager: Mapped[Optional["Employee"]] = relationship(
        remote_side=[id], back_populates="reportees", foreign_keys=[manager_id]
    )
    reportees: Mapped[List["Employee"]] = relationship(
        back_populates="manager", foreign_keys=[manager_id]
    )

    history: Mapped[List["EmployeeHistory"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    attendances: Mapped[List["Attendance"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    shift_assignments: Mapped[List["ShiftAssignment"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    leave_requests: Mapped[List["LeaveRequest"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="LeaveRequest.employee_id",
    )
    leave_balances: Mapped[List["LeaveBalance"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    salary_structures: Mapped[List["SalaryStructure"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    payslips: Mapped[List["Payslip"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="Document.employee_id",
    )
    predictions: Mapped[List["AttritionPrediction"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    risk_scores: Mapped[List["RiskScore"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    risk_alerts: Mapped[List["RiskAlert"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="RiskAlert.employee_id",
    )
    interventions: Mapped[List["InterventionPlan"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="InterventionPlan.employee_id",
    )
    performance_reviews: Mapped[List["PerformanceReview"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="PerformanceReview.employee_id",
    )
    goals: Mapped[List["Goal"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()

    @property
    def tenure_months(self) -> Optional[int]:
        if not self.date_of_joining:
            return None
        end = self.date_of_exit or date.today()
        return (end.year - self.date_of_joining.year) * 12 + (
            end.month - self.date_of_joining.month
        )

    def __repr__(self) -> str:
        return f"<Employee {self.employee_code} {self.full_name}>"


class EmployeeHistory(Base, TimestampMixin):
    """Immutable log of every material change to an employee record."""

    __tablename__ = "employee_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[EmployeeEventType] = mapped_column(
        enum_col(EmployeeEventType), nullable=False, index=True
    )
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    field_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    changed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    employee: Mapped["Employee"] = relationship(back_populates="history")

    def __repr__(self) -> str:
        return f"<EmployeeHistory emp={self.employee_id} {self.event_type}>"
