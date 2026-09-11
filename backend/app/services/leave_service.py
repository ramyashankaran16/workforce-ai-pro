"""
Leave: balance ledger, overlap detection, working-day counting, approval flow.

The balance ledger holds `allocated`, `carried_forward`, `used` and `pending`.
Applying moves days into `pending`; approval moves them from `pending` to
`used`; rejection or cancellation releases them. Available is therefore
(allocated + carried_forward) - (used + pending), which prevents two
simultaneous requests from both fitting inside one balance.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models.employee import Employee
from app.models.enums import LeaveDuration, LeaveStatus
from app.models.leave import LeaveBalance, LeaveRequest, LeaveType
from app.services import attendance_service
from app.utils.date_utils import utcnow


# ----------------------------------------------------------------- leave type
def get_leave_type(db: Session, leave_type_id: int) -> LeaveType:
    lt = db.get(LeaveType, leave_type_id)
    if lt is None or lt.is_deleted:
        raise NotFoundError("Leave type not found.")
    return lt


def create_leave_type(db: Session, data: dict) -> LeaveType:
    code = data["code"].upper().strip()
    if db.execute(select(LeaveType).where(LeaveType.code == code)).scalar_one_or_none():
        raise DuplicateError(f"Leave type code '{code}' is already in use.")
    if data.get("is_carry_forward") and data.get("max_carry_forward", 0) <= 0:
        raise BusinessRuleError(
            "max_carry_forward must be greater than zero when carry-forward is enabled."
        )

    lt = LeaveType(**{**data, "code": code})
    db.add(lt)
    db.commit()
    db.refresh(lt)
    return lt


# -------------------------------------------------------------------- balance
def get_or_create_balance(
    db: Session, employee_id: int, leave_type_id: int, year: int
) -> LeaveBalance:
    balance = db.execute(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
    ).scalar_one_or_none()

    if balance is None:
        leave_type = get_leave_type(db, leave_type_id)
        balance = LeaveBalance(
            employee_id=employee_id,
            leave_type_id=leave_type_id,
            year=year,
            allocated=leave_type.annual_quota,
        )
        db.add(balance)
        db.flush()
    return balance


def list_balances(db: Session, employee_id: int, year: int) -> List[dict]:
    """Every active leave type with the employee's balance, created on demand."""
    types = (
        db.execute(
            select(LeaveType).where(
                LeaveType.is_deleted.is_(False), LeaveType.is_active.is_(True)
            ).order_by(LeaveType.code)
        )
        .scalars()
        .all()
    )

    out = []
    for leave_type in types:
        balance = get_or_create_balance(db, employee_id, leave_type.id, year)
        out.append(
            {
                "id": balance.id,
                "employee_id": balance.employee_id,
                "leave_type_id": balance.leave_type_id,
                "year": balance.year,
                "allocated": balance.allocated,
                "carried_forward": balance.carried_forward,
                "used": balance.used,
                "pending": balance.pending,
                "available": balance.available,
                "leave_type_code": leave_type.code,
                "leave_type_name": leave_type.name,
            }
        )
    db.commit()
    return out


def allocate(db: Session, data: dict) -> LeaveBalance:
    balance = get_or_create_balance(
        db, data["employee_id"], data["leave_type_id"], data["year"]
    )
    balance.allocated = data["allocated"]
    balance.carried_forward = data.get("carried_forward", 0.0)
    db.commit()
    db.refresh(balance)
    return balance


# ------------------------------------------------------------ day calculation
def countable_days(
    db: Session, start: date, end: date, duration: LeaveDuration
) -> float:
    """
    Days actually deducted from the balance.

    Weekends and public holidays inside the range are not charged -- an
    employee taking Friday to Monday is charged two days, not four.
    """
    if duration in {LeaveDuration.FIRST_HALF, LeaveDuration.SECOND_HALF}:
        return 0.5

    holidays = attendance_service.holiday_dates(db, start, end)
    total = 0.0
    cursor = start
    while cursor <= end:
        if attendance_service.is_working_day(cursor, holidays):
            total += 1
        cursor += timedelta(days=1)
    return total


# ---------------------------------------------------------------------- apply
def apply_for_leave(db: Session, employee_id: int, data: dict) -> LeaveRequest:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    leave_type = get_leave_type(db, data["leave_type_id"])
    if not leave_type.is_active:
        raise BusinessRuleError(f"{leave_type.name} is not currently available.")

    start, end = data["start_date"], data["end_date"]

    # notice period
    if leave_type.min_notice_days:
        notice = (start - date.today()).days
        if notice < leave_type.min_notice_days:
            raise BusinessRuleError(
                f"{leave_type.name} requires {leave_type.min_notice_days} day(s) "
                f"of notice; this request gives {max(notice, 0)}."
            )

    # supporting document
    if leave_type.requires_document and not data.get("attachment_path"):
        raise BusinessRuleError(f"{leave_type.name} requires a supporting document.")

    total_days = countable_days(db, start, end, data["duration"])
    if total_days <= 0:
        raise BusinessRuleError(
            "That range contains no working days -- it is entirely weekend or holiday."
        )

    if leave_type.max_consecutive_days and total_days > leave_type.max_consecutive_days:
        raise BusinessRuleError(
            f"{leave_type.name} allows at most "
            f"{leave_type.max_consecutive_days} consecutive day(s)."
        )

    # overlap with an existing pending or approved request
    clash = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveStatus.PENDING, LeaveStatus.APPROVED]),
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
    ).scalars().first()
    if clash:
        raise BusinessRuleError(
            f"This overlaps an existing request ({clash.start_date} to "
            f"{clash.end_date}, {clash.status.value})."
        )

    # balance, unless the type is unpaid
    balance = get_or_create_balance(db, employee_id, leave_type.id, start.year)
    if leave_type.is_paid and balance.available < total_days:
        raise BusinessRuleError(
            f"Insufficient balance: {balance.available} day(s) available, "
            f"{total_days} requested."
        )

    request = LeaveRequest(
        employee_id=employee_id,
        leave_type_id=leave_type.id,
        start_date=start,
        end_date=end,
        duration=data["duration"],
        total_days=total_days,
        reason=data["reason"],
        contact_during_leave=data.get("contact_during_leave"),
        attachment_path=data.get("attachment_path"),
        approver_id=employee.manager_id,
        status=LeaveStatus.PENDING,
    )
    db.add(request)

    if leave_type.is_paid:
        balance.pending += total_days

    db.commit()
    db.refresh(request)
    return request


# ------------------------------------------------------------------- decision
def _assert_can_decide(db: Session, approver: Employee, request: LeaveRequest,
                       is_hr: bool) -> None:
    if is_hr:
        return
    target = db.get(Employee, request.employee_id)
    if target is None or target.manager_id != approver.id:
        raise PermissionDeniedError(
            "Only this employee's manager or HR can decide this request."
        )


def approve_leave(
    db: Session, request_id: int, approver: Employee, is_hr: bool,
    remarks: Optional[str] = None,
) -> LeaveRequest:
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise NotFoundError("Leave request not found.")
    if request.status != LeaveStatus.PENDING:
        raise BusinessRuleError(f"Request is already {request.status.value}.")

    _assert_can_decide(db, approver, request, is_hr)
    if request.employee_id == approver.id:
        raise BusinessRuleError("You cannot approve your own leave request.")

    leave_type = get_leave_type(db, request.leave_type_id)
    if leave_type.is_paid:
        balance = get_or_create_balance(
            db, request.employee_id, request.leave_type_id, request.start_date.year
        )
        balance.pending = max(balance.pending - request.total_days, 0)
        balance.used += request.total_days

    request.status = LeaveStatus.APPROVED
    request.approver_id = approver.id
    request.approved_at = utcnow()
    request.approver_remarks = remarks

    db.commit()
    db.refresh(request)
    return request


def reject_leave(
    db: Session, request_id: int, approver: Employee, is_hr: bool,
    remarks: Optional[str] = None,
) -> LeaveRequest:
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise NotFoundError("Leave request not found.")
    if request.status != LeaveStatus.PENDING:
        raise BusinessRuleError(f"Request is already {request.status.value}.")

    _assert_can_decide(db, approver, request, is_hr)

    leave_type = get_leave_type(db, request.leave_type_id)
    if leave_type.is_paid:
        balance = get_or_create_balance(
            db, request.employee_id, request.leave_type_id, request.start_date.year
        )
        balance.pending = max(balance.pending - request.total_days, 0)

    request.status = LeaveStatus.REJECTED
    request.approver_id = approver.id
    request.approved_at = utcnow()
    request.approver_remarks = remarks

    db.commit()
    db.refresh(request)
    return request


def cancel_leave(db: Session, request_id: int, employee_id: int) -> LeaveRequest:
    request = db.get(LeaveRequest, request_id)
    if request is None:
        raise NotFoundError("Leave request not found.")
    if request.employee_id != employee_id:
        raise PermissionDeniedError("You can only cancel your own requests.")
    if request.status not in {LeaveStatus.PENDING, LeaveStatus.APPROVED}:
        raise BusinessRuleError(f"Request is already {request.status.value}.")
    if request.status == LeaveStatus.APPROVED and request.start_date <= date.today():
        raise BusinessRuleError("Approved leave that has already started cannot be cancelled.")

    leave_type = get_leave_type(db, request.leave_type_id)
    if leave_type.is_paid:
        balance = get_or_create_balance(
            db, request.employee_id, request.leave_type_id, request.start_date.year
        )
        if request.status == LeaveStatus.PENDING:
            balance.pending = max(balance.pending - request.total_days, 0)
        else:
            balance.used = max(balance.used - request.total_days, 0)

    request.status = LeaveStatus.CANCELLED
    request.cancelled_at = utcnow()

    db.commit()
    db.refresh(request)
    return request


# ------------------------------------------------------------- carry forward
def run_carry_forward(db: Session, from_year: int) -> dict:
    """
    Roll unused balance into the next year, capped at max_carry_forward.

    Only types flagged is_carry_forward participate; everything else lapses.
    """
    to_year = from_year + 1
    types = {
        lt.id: lt
        for lt in db.execute(
            select(LeaveType).where(
                LeaveType.is_carry_forward.is_(True), LeaveType.is_deleted.is_(False)
            )
        ).scalars().all()
    }
    if not types:
        return {
            "from_year": from_year,
            "to_year": to_year,
            "employees_processed": 0,
            "balances_created": 0,
            "total_days_carried": 0.0,
        }

    balances = (
        db.execute(
            select(LeaveBalance).where(
                LeaveBalance.year == from_year,
                LeaveBalance.leave_type_id.in_(list(types.keys())),
            )
        )
        .scalars()
        .all()
    )

    employees = set()
    created = 0
    carried_total = 0.0

    for old in balances:
        leave_type = types[old.leave_type_id]
        remaining = max(old.allocated + old.carried_forward - old.used, 0)
        carry = min(remaining, leave_type.max_carry_forward)
        if carry <= 0:
            continue

        new_balance = get_or_create_balance(
            db, old.employee_id, old.leave_type_id, to_year
        )
        new_balance.carried_forward = carry
        new_balance.allocated = leave_type.annual_quota
        employees.add(old.employee_id)
        created += 1
        carried_total += carry

    db.commit()
    return {
        "from_year": from_year,
        "to_year": to_year,
        "employees_processed": len(employees),
        "balances_created": created,
        "total_days_carried": round(carried_total, 2),
    }
