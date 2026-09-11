"""Salary structures, payroll runs and payslips."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import PayComponentType, PayFrequency, PayrollStatus, enum_col
from app.models.mixins import TimestampMixin


class SalaryComponent(Base, TimestampMixin):
    """Reusable earning/deduction definition, e.g. HRA, PF, Professional Tax."""

    __tablename__ = "salary_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    component_type: Mapped[PayComponentType] = mapped_column(
        enum_col(PayComponentType), nullable=False
    )
    is_percentage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    percentage_of: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    default_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    is_taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<SalaryComponent {self.code}>"


class SalaryStructure(Base, TimestampMixin):
    """Effective-dated compensation package for one employee."""

    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    ctc: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    basic_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    hra: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    conveyance_allowance: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    medical_allowance: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    special_allowance: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    provident_fund: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    professional_tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    income_tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    other_deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    pay_frequency: Mapped[PayFrequency] = mapped_column(
        enum_col(PayFrequency), default=PayFrequency.MONTHLY, nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    bank_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    bank_account_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pan_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    employee: Mapped["Employee"] = relationship(back_populates="salary_structures")

    def __repr__(self) -> str:
        return f"<SalaryStructure emp={self.employee_id} ctc={self.ctc}>"


class PayrollRun(Base, TimestampMixin):
    """A monthly batch that generates payslips for all eligible employees."""

    __tablename__ = "payroll_runs"
    __table_args__ = (UniqueConstraint("month", "year", name="uq_payroll_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[PayrollStatus] = mapped_column(
        enum_col(PayrollStatus), default=PayrollStatus.DRAFT, nullable=False, index=True
    )
    total_employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_gross: Mapped[float] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    total_net: Mapped[float] = mapped_column(Numeric(16, 2), default=0, nullable=False)

    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    processed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    payslips: Mapped[List["Payslip"]] = relationship(
        back_populates="payroll_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PayrollRun {self.month}/{self.year} {self.status}>"


class Payslip(Base, TimestampMixin):
    """One employee's pay for one payroll run."""

    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payslip_employee_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payroll_run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slip_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    working_days: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    present_days: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    paid_leave_days: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unpaid_leave_days: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    overtime_hours: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    gross_earnings: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    net_pay: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)

    status: Mapped[PayrollStatus] = mapped_column(
        enum_col(PayrollStatus), default=PayrollStatus.DRAFT, nullable=False
    )
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    payroll_run: Mapped["PayrollRun"] = relationship(back_populates="payslips")
    employee: Mapped["Employee"] = relationship(back_populates="payslips")
    line_items: Mapped[List["PayslipItem"]] = relationship(
        back_populates="payslip", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Payslip {self.slip_number}>"


class PayslipItem(Base):
    """A single earning or deduction line on a payslip."""

    __tablename__ = "payslip_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payslip_id: Mapped[int] = mapped_column(
        ForeignKey("payslips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_name: Mapped[str] = mapped_column(String(80), nullable=False)
    component_type: Mapped[PayComponentType] = mapped_column(
        enum_col(PayComponentType), nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    payslip: Mapped["Payslip"] = relationship(back_populates="line_items")

    def __repr__(self) -> str:
        return f"<PayslipItem {self.component_name} {self.amount}>"
