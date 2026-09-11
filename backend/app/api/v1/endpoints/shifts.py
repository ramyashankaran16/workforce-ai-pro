"""Shift and roster endpoints."""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.attendance import Shift
from app.models.user import User
from app.schemas.attendance import (
    RosterEntry,
    ShiftAssignCreate,
    ShiftAssignmentRead,
    ShiftCreate,
    ShiftRead,
    ShiftUpdate,
)
from app.schemas.common import MessageResponse
from app.services import shift_service

router = APIRouter(prefix="/shifts", tags=["Shifts"])


@router.get("", response_model=Page[ShiftRead], summary="List shifts")
def list_shifts(
    params: PaginationParams = Depends(),
    is_active: Optional[bool] = Query(None),
    _: User = Depends(RequirePermissions("attendance:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Shift).where(Shift.is_deleted.is_(False))
    if is_active is not None:
        stmt = stmt.where(Shift.is_active.is_(is_active))
    stmt = stmt.order_by(Shift.start_time)
    rows, total = paginate(db, stmt, params)
    return Page[ShiftRead].create(
        [ShiftRead.model_validate(r) for r in rows], total, params
    )


@router.get("/roster", response_model=List[RosterEntry], summary="Roster for a date")
def roster(
    on: date = Query(..., description="Date to build the roster for"),
    department_id: Optional[int] = Query(None),
    _: User = Depends(RequirePermissions("attendance:read_all")),
    db: Session = Depends(get_db),
):
    return shift_service.build_roster(db, on, department_id)


@router.get("/{shift_id}", response_model=ShiftRead, summary="Get a shift")
def get_shift(
    shift_id: int,
    _: User = Depends(RequirePermissions("attendance:read")),
    db: Session = Depends(get_db),
):
    return shift_service.get_shift(db, shift_id)


@router.post(
    "",
    response_model=ShiftRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a shift",
)
def create_shift(
    payload: ShiftCreate,
    _: User = Depends(RequirePermissions("shift:manage")),
    db: Session = Depends(get_db),
):
    """`working_hours` and `is_night_shift` are derived from the times, not supplied."""
    return shift_service.create_shift(db, payload.model_dump())


@router.patch("/{shift_id}", response_model=ShiftRead, summary="Update a shift")
def update_shift(
    shift_id: int,
    payload: ShiftUpdate,
    _: User = Depends(RequirePermissions("shift:manage")),
    db: Session = Depends(get_db),
):
    return shift_service.update_shift(
        db, shift_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/{shift_id}", response_model=MessageResponse, summary="Delete a shift")
def delete_shift(
    shift_id: int,
    _: User = Depends(RequirePermissions("shift:manage")),
    db: Session = Depends(get_db),
):
    shift_service.delete_shift(db, shift_id)
    return MessageResponse(message="Shift deleted.")


@router.post(
    "/{shift_id}/assign",
    response_model=List[ShiftAssignmentRead],
    summary="Assign a shift to employees",
)
def assign_shift(
    shift_id: int,
    payload: ShiftAssignCreate,
    current_user: User = Depends(RequirePermissions("shift:manage")),
    db: Session = Depends(get_db),
):
    """Rejects any assignment overlapping an existing active one for the same employee."""
    return shift_service.assign_shift(
        db,
        shift_id,
        payload.employee_ids,
        payload.start_date,
        payload.end_date,
        actor_id=current_user.id,
    )
