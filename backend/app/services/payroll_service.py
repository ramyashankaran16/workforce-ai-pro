"""
Payroll computation.

Money is handled as Decimal end to end and quantised to two places at each
step. Float would accumulate representation error across thousands of payslips
-- 0.1 + 0.2 is not 0.3 in binary floating point, and a payslip that is a paisa
out is a payslip that fails reconciliation.

Immutability rule: once a run is paid, its payslips never change. A correction
discovered later becomes an arrears line on the next run, which keeps the
payslip matching what actually left the bank.
"""

import calendar
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
)
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.enums import (
    AttendanceStatus,
    LeaveStatus,
    PayComponentType,
    PayrollStatus,
)
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import PayrollRun, Payslip, PayslipItem, SalaryStructure
from app.services import attendance_service
from app.utils.code_generator import generate_payroll_reference, generate_payslip_number
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")
OVERTIME_MULTIPLIER = Decimal("1.5")
STANDARD_DAY_HOURS = Decimal("8")

# A run in one of these states is closed to further computation.
LOCKED_STATUSES = {PayrollStatus.APPROVED, PayrollStatus.PAID}


def money(value) -> Decimal:
    """Coerce to Decimal and round half-up to two places."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value or 0))
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# ----------------------------------------------------------- salary structure
def active_structure(
    db: Session, employee_id: int, on: date
) -> Optional[SalaryStructure]:
    """The structure in force on a given date."""
    return db.execute(
        select(SalaryStructure)
        .where(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.effective_from <= on,
            or_(
                SalaryStructure.effective_to.is_(None),
                SalaryStructure.effective_to >= on,
            ),
        )
        .order_by(SalaryStructure.effective_from.desc())
    ).scalars().first()


def create_structure(
    db: Session, data: dict, actor_id: Optional[int] = None
) -> SalaryStructure:
    """
    Create an effective-dated structure, closing the previous one.

    History is preserved rather than overwritten, so a payslip generated last
    March can still be explained with the figures that applied then.
    """
    employee = db.get(Employee, data["employee_id"])
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    effective_from = data["effective_from"]

    previous = db.execute(
        select(SalaryStructure)
        .where(
            SalaryStructure.employee_id == employee.id,
            SalaryStructure.is_active.is_(True),
        )
        .order_by(SalaryStructure.effective_from.desc())
    ).scalars().first()

    if previous:
        if previous.effective_from >= effective_from:
            raise BusinessRuleError(
                f"A structure already applies from {previous.effective_from}. "
                "The new effective date must be later."
            )
        previous.effective_to = effective_from - __import__("datetime").timedelta(days=1)
        previous.is_active = False

    structure = SalaryStructure(**data, created_by_id=actor_id, is_active=True)
    db.add(structure)

    # keep the denormalised snapshot on the employee in step
    employee.current_salary = money(data["ctc"])

    db.commit()
    db.refresh(structure)
    return structure


def structure_totals(structure: SalaryStructure) -> Dict[str, Decimal]:
    gross = money(
        money(structure.basic_salary)
        + money(structure.hra)
        + money(structure.conveyance_allowance)
        + money(structure.medical_allowance)
        + money(structure.special_allowance)
    )
    deductions = money(
        money(structure.provident_fund)
        + money(structure.professional_tax)
        + money(structure.income_tax)
        + money(structure.other_deductions)
    )
    return {
        "gross_earnings": gross,
        "total_deductions": deductions,
        "net_monthly": money(gross - deductions),
    }


# ---------------------------------------------------------------- payroll run
def period_bounds(month: int, year: int) -> Tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def get_run(db: Session, run_id: int) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None:
        raise NotFoundError("Payroll run not found.")
    return run


def create_run(db: Session, month: int, year: int, notes: Optional[str] = None) -> PayrollRun:
    existing = db.execute(
        select(PayrollRun).where(PayrollRun.month == month, PayrollRun.year == year)
    ).scalar_one_or_none()
    if existing:
        raise DuplicateError(
            f"A payroll run for {month:02d}/{year} already exists "
            f"({existing.reference}, {existing.status.value})."
        )

    start, end = period_bounds(month, year)
    run = PayrollRun(
        reference=generate_payroll_reference(year, month),
        month=month,
        year=year,
        period_start=start,
        period_end=end,
        status=PayrollStatus.DRAFT,
        notes=notes,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ----------------------------------------------------------- attendance input
def _period_attendance(
    db: Session, employee_id: int, start: date, end: date
) -> Dict[str, float]:
    """Days actually worked, on paid leave, and lost, for one period."""
    records = (
        db.execute(
            select(Attendance).where(
                Attendance.employee_id == employee_id,
                Attendance.attendance_date >= start,
                Attendance.attendance_date <= end,
            )
        )
        .scalars()
        .all()
    )

    present = sum(
        1
        for r in records
        if r.status
        in {
            AttendanceStatus.PRESENT,
            AttendanceStatus.LATE,
            AttendanceStatus.WORK_FROM_HOME,
        }
    )
    half_days = sum(1 for r in records if r.status == AttendanceStatus.HALF_DAY)
    absent = sum(1 for r in records if r.status == AttendanceStatus.ABSENT)
    overtime = sum(r.overtime_hours for r in records)

    # Split approved leave in the period into paid and unpaid.
    paid_leave = 0.0
    unpaid_leave = 0.0
    leaves = (
        db.execute(
            select(LeaveRequest, LeaveType)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
        .all()
    )
    for request, leave_type in leaves:
        # only the portion falling inside this period counts
        overlap_start = max(request.start_date, start)
        overlap_end = min(request.end_date, end)
        days = attendance_service.working_days_between(db, overlap_start, overlap_end)
        if request.total_days < 1:  # half day
            days = request.total_days
        if leave_type.is_paid:
            paid_leave += days
        else:
            unpaid_leave += days

    return {
        "present_days": present + (half_days * 0.5),
        "half_days": half_days,
        "paid_leave_days": paid_leave,
        # An absent day and an unpaid leave day both cost pay. Half days lose
        # the other half.
        "unpaid_leave_days": unpaid_leave + absent + (half_days * 0.5),
        "overtime_hours": round(overtime, 2),
    }


# -------------------------------------------------------------------- compute
def compute_payslip_lines(
    structure: SalaryStructure,
    working_days: int,
    unpaid_days: float,
    overtime_hours: float,
) -> Tuple[List[dict], Decimal, Decimal, Decimal]:
    """
    Build the line items and totals for one payslip.

    Loss of pay is charged at gross / working_days, so a month with fewer
    working days has a higher per-day rate -- which is the point: the salary
    buys that month's working days, not a notional thirty.
    """
    totals = structure_totals(structure)
    gross_full = totals["gross_earnings"]

    lines: List[dict] = []
    order = 0

    for name, amount in [
        ("Basic Salary", structure.basic_salary),
        ("House Rent Allowance", structure.hra),
        ("Conveyance Allowance", structure.conveyance_allowance),
        ("Medical Allowance", structure.medical_allowance),
        ("Special Allowance", structure.special_allowance),
    ]:
        value = money(amount)
        if value > 0:
            order += 1
            lines.append(
                {
                    "component_name": name,
                    "component_type": PayComponentType.EARNING,
                    "amount": value,
                    "display_order": order,
                }
            )

    # overtime, paid at 1.5x the basic hourly rate
    overtime_pay = Decimal("0")
    if overtime_hours > 0 and working_days > 0:
        hourly = money(
            money(structure.basic_salary) / Decimal(working_days) / STANDARD_DAY_HOURS
        )
        overtime_pay = money(
            hourly * Decimal(str(overtime_hours)) * OVERTIME_MULTIPLIER
        )
        order += 1
        lines.append(
            {
                "component_name": f"Overtime ({overtime_hours} hrs)",
                "component_type": PayComponentType.EARNING,
                "amount": overtime_pay,
                "display_order": order,
            }
        )

    gross = money(gross_full + overtime_pay)

    # deductions
    order = 100
    deductions = Decimal("0")
    for name, amount in [
        ("Provident Fund", structure.provident_fund),
        ("Professional Tax", structure.professional_tax),
        ("Income Tax (TDS)", structure.income_tax),
        ("Other Deductions", structure.other_deductions),
    ]:
        value = money(amount)
        if value > 0:
            order += 1
            deductions += value
            lines.append(
                {
                    "component_name": name,
                    "component_type": PayComponentType.DEDUCTION,
                    "amount": value,
                    "display_order": order,
                }
            )

    if unpaid_days > 0 and working_days > 0:
        per_day = money(gross_full / Decimal(working_days))
        lop = money(per_day * Decimal(str(unpaid_days)))
        lop = min(lop, gross)  # never charge more than was earned
        order += 1
        deductions += lop
        lines.append(
            {
                "component_name": f"Loss of Pay ({unpaid_days} day(s))",
                "component_type": PayComponentType.DEDUCTION,
                "amount": lop,
                "display_order": order,
            }
        )

    deductions = money(deductions)
    net = money(gross - deductions)
    return lines, gross, deductions, net


def process_run(db: Session, run_id: int, actor_id: Optional[int] = None) -> dict:
    """Generate payslips for every eligible employee in the period."""
    run = get_run(db, run_id)
    if run.status in LOCKED_STATUSES:
        raise BusinessRuleError(
            f"Run {run.reference} is {run.status.value} and cannot be reprocessed."
        )

    # reprocessing a draft discards the previous attempt
    for old in list(run.payslips):
        db.delete(old)
    db.flush()

    run.status = PayrollStatus.PROCESSING
    db.commit()

    working_days = attendance_service.working_days_between(
        db, run.period_start, run.period_end
    )

    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False),
                Employee.date_of_joining <= run.period_end,
                or_(
                    Employee.date_of_exit.is_(None),
                    Employee.date_of_exit >= run.period_start,
                ),
            ).order_by(Employee.employee_code)
        )
        .scalars()
        .all()
    )

    created = 0
    skipped: List[str] = []
    total_gross = Decimal("0")
    total_deductions = Decimal("0")
    total_net = Decimal("0")

    try:
        for employee in employees:
            structure = active_structure(db, employee.id, run.period_end)
            if structure is None:
                skipped.append(
                    f"{employee.employee_code}: no salary structure in force"
                )
                continue

            stats = _period_attendance(
                db, employee.id, run.period_start, run.period_end
            )
            lines, gross, deductions, net = compute_payslip_lines(
                structure,
                working_days,
                stats["unpaid_leave_days"],
                stats["overtime_hours"],
            )

            payslip = Payslip(
                payroll_run_id=run.id,
                employee_id=employee.id,
                slip_number=generate_payslip_number(db, run.year, run.month),
                working_days=working_days,
                present_days=stats["present_days"],
                paid_leave_days=stats["paid_leave_days"],
                unpaid_leave_days=stats["unpaid_leave_days"],
                overtime_hours=stats["overtime_hours"],
                gross_earnings=gross,
                total_deductions=deductions,
                net_pay=net,
                status=PayrollStatus.PROCESSED,
            )
            db.add(payslip)
            db.flush()

            for line in lines:
                db.add(PayslipItem(payslip_id=payslip.id, **line))

            created += 1
            total_gross += gross
            total_deductions += deductions
            total_net += net

        run.total_employees = created
        run.total_gross = money(total_gross)
        run.total_deductions = money(total_deductions)
        run.total_net = money(total_net)
        run.status = PayrollStatus.PROCESSED
        run.processed_at = utcnow()
        run.processed_by_id = actor_id
        run.error_message = None
        db.commit()
    except Exception as exc:
        db.rollback()
        run = get_run(db, run_id)
        run.status = PayrollStatus.FAILED
        run.error_message = str(exc)[:500]
        db.commit()
        logger.exception("Payroll run %s failed", run.reference)
        raise

    db.refresh(run)
    return {
        "run": run,
        "payslips_created": created,
        "employees_skipped": len(skipped),
        "skipped_reasons": skipped[:20],
    }


def approve_run(db: Session, run_id: int, actor_id: int) -> PayrollRun:
    run = get_run(db, run_id)
    if run.status != PayrollStatus.PROCESSED:
        raise BusinessRuleError(
            f"Only a processed run can be approved; this one is {run.status.value}."
        )
    run.status = PayrollStatus.APPROVED
    run.approved_by_id = actor_id
    for payslip in run.payslips:
        payslip.status = PayrollStatus.APPROVED
    db.commit()
    db.refresh(run)
    return run


def mark_paid(db: Session, run_id: int) -> PayrollRun:
    run = get_run(db, run_id)
    if run.status != PayrollStatus.APPROVED:
        raise BusinessRuleError(
            f"Only an approved run can be marked paid; this one is {run.status.value}."
        )
    run.status = PayrollStatus.PAID
    run.paid_at = utcnow()
    for payslip in run.payslips:
        payslip.status = PayrollStatus.PAID
    db.commit()
    db.refresh(run)
    return run


def add_adjustment(db: Session, payslip_id: int, data: dict) -> Payslip:
    """
    Add an arrears or recovery line to a payslip in an open run.

    This is how a correction discovered after payment is handled: it lands on
    the next cycle rather than rewriting a payslip that has already been paid.
    """
    payslip = db.get(Payslip, payslip_id)
    if payslip is None:
        raise NotFoundError("Payslip not found.")

    run = get_run(db, payslip.payroll_run_id)
    if run.status in LOCKED_STATUSES:
        raise BusinessRuleError(
            f"Run {run.reference} is {run.status.value}. Add this as an "
            "adjustment on the next run instead."
        )

    amount = money(data["amount"])
    highest = db.execute(
        select(func.max(PayslipItem.display_order)).where(
            PayslipItem.payslip_id == payslip.id
        )
    ).scalar() or 0

    db.add(
        PayslipItem(
            payslip_id=payslip.id,
            component_name=data["component_name"],
            component_type=data["component_type"],
            amount=amount,
            display_order=highest + 1,
        )
    )

    if data["component_type"] == PayComponentType.EARNING:
        payslip.gross_earnings = money(money(payslip.gross_earnings) + amount)
    else:
        payslip.total_deductions = money(money(payslip.total_deductions) + amount)

    payslip.net_pay = money(
        money(payslip.gross_earnings) - money(payslip.total_deductions)
    )
    if data.get("remarks"):
        payslip.remarks = data["remarks"]

    # keep the run totals consistent
    _recalculate_run_totals(db, run)
    db.commit()
    db.refresh(payslip)
    return payslip


def _recalculate_run_totals(db: Session, run: PayrollRun) -> None:
    payslips = (
        db.execute(select(Payslip).where(Payslip.payroll_run_id == run.id))
        .scalars()
        .all()
    )
    run.total_employees = len(payslips)
    run.total_gross = money(sum((money(p.gross_earnings) for p in payslips), Decimal("0")))
    run.total_deductions = money(
        sum((money(p.total_deductions) for p in payslips), Decimal("0"))
    )
    run.total_net = money(sum((money(p.net_pay) for p in payslips), Decimal("0")))


def run_summary(db: Session, run_id: int) -> dict:
    run = get_run(db, run_id)
    nets = (
        db.execute(select(Payslip.net_pay).where(Payslip.payroll_run_id == run.id))
        .scalars()
        .all()
    )
    values = [money(n) for n in nets] or [Decimal("0")]
    return {
        "month": run.month,
        "year": run.year,
        "status": run.status,
        "total_employees": run.total_employees,
        "total_gross": money(run.total_gross),
        "total_deductions": money(run.total_deductions),
        "total_net": money(run.total_net),
        "average_net": money(sum(values, Decimal("0")) / Decimal(len(values))),
        "highest_net": max(values),
        "lowest_net": min(values),
    }


def build_payslip_detail(db: Session, payslip: Payslip) -> dict:
    run = db.get(PayrollRun, payslip.payroll_run_id)
    employee = db.get(Employee, payslip.employee_id)
    payload = {c.name: getattr(payslip, c.name) for c in payslip.__table__.columns}
    payload.update(
        {
            "employee_code": employee.employee_code if employee else None,
            "employee_name": employee.full_name if employee else None,
            "department_name": (
                employee.department.name if employee and employee.department else None
            ),
            "designation_title": (
                employee.designation.title if employee and employee.designation else None
            ),
            "month": run.month if run else None,
            "year": run.year if run else None,
            "period_start": run.period_start if run else None,
            "period_end": run.period_end if run else None,
            "line_items": sorted(payslip.line_items, key=lambda i: i.display_order),
        }
    )
    return payload
