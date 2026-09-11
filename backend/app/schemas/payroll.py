"""Salary structure, payroll run and payslip schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.enums import PayComponentType, PayFrequency, PayrollStatus
from app.schemas.common import ORMBase

Money = Decimal


# ------------------------------------------------------------ salary structure
class SalaryStructureCreate(BaseModel):
    employee_id: int
    ctc: Money = Field(..., ge=0, decimal_places=2)
    basic_salary: Money = Field(..., gt=0, decimal_places=2)
    hra: Money = Field(0, ge=0, decimal_places=2)
    conveyance_allowance: Money = Field(0, ge=0, decimal_places=2)
    medical_allowance: Money = Field(0, ge=0, decimal_places=2)
    special_allowance: Money = Field(0, ge=0, decimal_places=2)

    provident_fund: Money = Field(0, ge=0, decimal_places=2)
    professional_tax: Money = Field(0, ge=0, decimal_places=2)
    income_tax: Money = Field(0, ge=0, decimal_places=2)
    other_deductions: Money = Field(0, ge=0, decimal_places=2)

    pay_frequency: PayFrequency = PayFrequency.MONTHLY
    effective_from: date

    bank_name: Optional[str] = Field(None, max_length=120)
    bank_account_number: Optional[str] = Field(None, max_length=40)
    ifsc_code: Optional[str] = Field(None, max_length=20)
    pan_number: Optional[str] = Field(None, max_length=20)

    @model_validator(mode="after")
    def deductions_within_gross(self):
        gross = (
            self.basic_salary + self.hra + self.conveyance_allowance
            + self.medical_allowance + self.special_allowance
        )
        deductions = (
            self.provident_fund + self.professional_tax
            + self.income_tax + self.other_deductions
        )
        if deductions > gross:
            raise ValueError("Total deductions cannot exceed gross earnings.")
        return self


class SalaryStructureRead(ORMBase):
    id: int
    employee_id: int
    ctc: Money
    basic_salary: Money
    hra: Money
    conveyance_allowance: Money
    medical_allowance: Money
    special_allowance: Money
    provident_fund: Money
    professional_tax: Money
    income_tax: Money
    other_deductions: Money
    pay_frequency: PayFrequency
    effective_from: date
    effective_to: Optional[date] = None
    is_active: bool
    bank_name: Optional[str] = None
    ifsc_code: Optional[str] = None
    gross_earnings: Optional[Money] = None
    total_deductions: Optional[Money] = None
    net_monthly: Optional[Money] = None


# ---------------------------------------------------------------- payroll run
class PayrollRunCreate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)
    notes: Optional[str] = None


class PayrollRunRead(ORMBase):
    id: int
    reference: str
    month: int
    year: int
    period_start: date
    period_end: date
    status: PayrollStatus
    total_employees: int
    total_gross: Money
    total_deductions: Money
    total_net: Money
    processed_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    error_message: Optional[str] = None
    notes: Optional[str] = None


class ProcessResult(BaseModel):
    run: PayrollRunRead
    payslips_created: int
    employees_skipped: int
    skipped_reasons: List[str] = []


# -------------------------------------------------------------------- payslip
class PayslipItemRead(ORMBase):
    id: int
    component_name: str
    component_type: PayComponentType
    amount: Money
    display_order: int


class PayslipRead(ORMBase):
    id: int
    payroll_run_id: int
    employee_id: int
    slip_number: str
    working_days: float
    present_days: float
    paid_leave_days: float
    unpaid_leave_days: float
    overtime_hours: float
    gross_earnings: Money
    total_deductions: Money
    net_pay: Money
    status: PayrollStatus
    remarks: Optional[str] = None


class PayslipDetail(PayslipRead):
    employee_code: Optional[str] = None
    employee_name: Optional[str] = None
    department_name: Optional[str] = None
    designation_title: Optional[str] = None
    month: Optional[int] = None
    year: Optional[int] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    line_items: List[PayslipItemRead] = []


class AdjustmentCreate(BaseModel):
    """An ad-hoc earning or deduction, e.g. arrears from a corrected period."""

    component_name: str = Field(..., min_length=2, max_length=80)
    component_type: PayComponentType
    amount: Money = Field(..., gt=0, decimal_places=2)
    remarks: Optional[str] = None


class PayrollSummary(BaseModel):
    month: int
    year: int
    status: PayrollStatus
    total_employees: int
    total_gross: Money
    total_deductions: Money
    total_net: Money
    average_net: Money
    highest_net: Money
    lowest_net: Money
