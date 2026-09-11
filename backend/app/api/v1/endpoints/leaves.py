"""Leave endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import (
    RequirePermissions,
    get_current_employee,
    get_current_user,
)
from app.core.exceptions import PermissionDeniedError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import LeaveStatus
from app.models.leave import LeaveRequest, LeaveType
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.leave import (
    BalanceAllocation,
    CarryForwardResult,
    LeaveApply,
    LeaveBalanceRead,
    LeaveDecision,
    LeaveRequestRead,
    LeaveTypeCreate,
    LeaveTypeRead,
    LeaveTypeUpdate,
)
from app.services import employee_service, leave_service

router = APIRouter(prefix="/leaves", tags=["Leave"])


# ----------------------------------------------------------------- leave types
@router.get("/types", response_model=List[LeaveTypeRead], summary="List leave types")
def list_types(
    is_active: Optional[bool] = Query(True),
    _: User = Depends(RequirePermissions("leave:read")),
    db: Session = Depends(get_db),
):
    stmt = select(LeaveType).where(LeaveType.is_deleted.is_(False))
    if is_active is not None:
        stmt = stmt.where(LeaveType.is_active.is_(is_active))
    return db.execute(stmt.order_by(LeaveType.code)).scalars().all()


@router.post(
    "/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a leave type",
)
def create_type(
    payload: LeaveTypeCreate,
    _: User = Depends(RequirePermissions("leave:manage")),
    db: Session = Depends(get_db),
):
    return leave_service.create_leave_type(db, payload.model_dump())


@router.patch("/types/{type_id}", response_model=LeaveTypeRead, summary="Update a type")
def update_type(
    type_id: int,
    payload: LeaveTypeUpdate,
    _: User = Depends(RequirePermissions("leave:manage")),
    db: Session = Depends(get_db),
):
    leave_type = leave_service.get_leave_type(db, type_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(leave_type, field, value)
    db.commit()
    db.refresh(leave_type)
    return leave_type


# -------------------------------------------------------------------- balances
@router.get(
    "/balance",
    response_model=List[LeaveBalanceRead],
    summary="Own leave balances for a year",
)
def my_balance(
    year: int = Query(default_factory=lambda: date.today().year),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """`available` = (allocated + carried_forward) - (used + pending)."""
    return leave_service.list_balances(db, employee.id, year)


@router.get(
    "/balance/{employee_id}",
    response_model=List[LeaveBalanceRead],
    summary="Balances for one employee",
)
def employee_balance(
    employee_id: int,
    year: int = Query(default_factory=lambda: date.today().year),
    current_user: User = Depends(RequirePermissions("leave:read_team", "leave:read_all", require_all=False)),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)
    return leave_service.list_balances(db, employee_id, year)


@router.post(
    "/balance/allocate",
    response_model=LeaveBalanceRead,
    summary="Allocate or adjust a balance (HR)",
)
def allocate_balance(
    payload: BalanceAllocation,
    _: User = Depends(RequirePermissions("leave:manage")),
    db: Session = Depends(get_db),
):
    balance = leave_service.allocate(db, payload.model_dump())
    leave_type = leave_service.get_leave_type(db, balance.leave_type_id)
    return {
        **{c.name: getattr(balance, c.name) for c in balance.__table__.columns},
        "available": balance.available,
        "leave_type_code": leave_type.code,
        "leave_type_name": leave_type.name,
    }


# --------------------------------------------------------------------- requests
@router.post(
    "",
    response_model=LeaveRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Apply for leave",
)
def apply_leave(
    payload: LeaveApply,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    """
    Weekends and public holidays inside the range are not charged. Days move
    into `pending` immediately so a second overlapping request cannot also fit.
    """
    return leave_service.apply_for_leave(db, employee.id, payload.model_dump())


@router.get("/me", response_model=Page[LeaveRequestRead], summary="Own requests")
def my_requests(
    params: PaginationParams = Depends(),
    status_filter: Optional[LeaveStatus] = Query(None, alias="status"),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    stmt = select(LeaveRequest).where(LeaveRequest.employee_id == employee.id)
    if status_filter:
        stmt = stmt.where(LeaveRequest.status == status_filter)
    stmt = stmt.order_by(LeaveRequest.start_date.desc())

    rows, total = paginate(db, stmt, params)
    return Page[LeaveRequestRead].create(
        [LeaveRequestRead.model_validate(r) for r in rows], total, params
    )


@router.get("", response_model=Page[LeaveRequestRead], summary="List requests (scoped)")
def list_requests(
    params: PaginationParams = Depends(),
    employee_id: Optional[int] = Query(None),
    status_filter: Optional[LeaveStatus] = Query(None, alias="status"),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    current_user: User = Depends(RequirePermissions("leave:read_team", "leave:read_all", require_all=False)),
    db: Session = Depends(get_db),
):
    visible_ids = db.execute(
        employee_service.scope_query(db, select(Employee.id), current_user)
    ).scalars().all()

    stmt = select(LeaveRequest).where(LeaveRequest.employee_id.in_(visible_ids))
    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status_filter:
        stmt = stmt.where(LeaveRequest.status == status_filter)
    if start:
        stmt = stmt.where(LeaveRequest.end_date >= start)
    if end:
        stmt = stmt.where(LeaveRequest.start_date <= end)

    stmt = stmt.order_by(LeaveRequest.start_date.desc())
    rows, total = paginate(db, stmt, params)
    return Page[LeaveRequestRead].create(
        [LeaveRequestRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/pending",
    response_model=Page[LeaveRequestRead],
    summary="Approval queue for the current approver",
)
def pending_queue(
    params: PaginationParams = Depends(),
    current_user: User = Depends(RequirePermissions("leave:approve")),
    db: Session = Depends(get_db),
):
    stmt = select(LeaveRequest).where(LeaveRequest.status == LeaveStatus.PENDING)

    role = (current_user.role_name or "").lower()
    if role not in {"admin", "hr"}:
        profile = employee_service.get_by_user(db, current_user.id)
        if profile is None:
            raise PermissionDeniedError("No employee profile is linked to this account.")
        reportee_ids = db.execute(
            select(Employee.id).where(Employee.manager_id == profile.id)
        ).scalars().all()
        stmt = stmt.where(LeaveRequest.employee_id.in_(reportee_ids))

    stmt = stmt.order_by(LeaveRequest.start_date)
    rows, total = paginate(db, stmt, params)
    return Page[LeaveRequestRead].create(
        [LeaveRequestRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/{request_id}/approve", response_model=LeaveRequestRead, summary="Approve"
)
def approve(
    request_id: int,
    payload: LeaveDecision,
    current_user: User = Depends(RequirePermissions("leave:approve")),
    db: Session = Depends(get_db),
):
    """Moves the days from `pending` to `used`."""
    approver = employee_service.get_by_user(db, current_user.id)
    if approver is None:
        raise PermissionDeniedError("No employee profile is linked to this account.")
    is_hr = (current_user.role_name or "").lower() in {"admin", "hr"}
    return leave_service.approve_leave(db, request_id, approver, is_hr, payload.remarks)


@router.post("/{request_id}/reject", response_model=LeaveRequestRead, summary="Reject")
def reject(
    request_id: int,
    payload: LeaveDecision,
    current_user: User = Depends(RequirePermissions("leave:approve")),
    db: Session = Depends(get_db),
):
    """Releases the reserved days back to the balance."""
    approver = employee_service.get_by_user(db, current_user.id)
    if approver is None:
        raise PermissionDeniedError("No employee profile is linked to this account.")
    is_hr = (current_user.role_name or "").lower() in {"admin", "hr"}
    return leave_service.reject_leave(db, request_id, approver, is_hr, payload.remarks)


@router.post(
    "/{request_id}/cancel", response_model=LeaveRequestRead, summary="Cancel own request"
)
def cancel(
    request_id: int,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return leave_service.cancel_leave(db, request_id, employee.id)


@router.post(
    "/carry-forward",
    response_model=CarryForwardResult,
    summary="Roll unused balance into the next year",
)
def carry_forward(
    from_year: int = Query(..., ge=2000, le=2100),
    _: User = Depends(RequirePermissions("leave:manage")),
    db: Session = Depends(get_db),
):
    """Only types flagged `is_carry_forward` participate, capped at `max_carry_forward`."""
    return leave_service.run_carry_forward(db, from_year)
