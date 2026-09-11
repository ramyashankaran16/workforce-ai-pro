"""Designation endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.department import Designation
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.department import (
    DesignationCreate,
    DesignationRead,
    DesignationUpdate,
)
from app.services import department_service

router = APIRouter(prefix="/designations", tags=["Designations"])


@router.get("", response_model=Page[DesignationRead], summary="List designations")
def list_designations(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Match title or code"),
    department_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    _: User = Depends(RequirePermissions("department:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Designation).where(Designation.is_deleted.is_(False))
    if search:
        stmt = stmt.where(Designation.title.ilike(f"%{search.strip()}%"))
    if department_id is not None:
        stmt = stmt.where(Designation.department_id == department_id)
    if is_active is not None:
        stmt = stmt.where(Designation.is_active.is_(is_active))

    stmt = stmt.order_by(Designation.level, Designation.title)
    rows, total = paginate(db, stmt, params)
    return Page[DesignationRead].create(
        [DesignationRead.model_validate(r) for r in rows], total, params
    )


@router.get("/{designation_id}", response_model=DesignationRead, summary="Get one")
def get_designation(
    designation_id: int,
    _: User = Depends(RequirePermissions("department:read")),
    db: Session = Depends(get_db),
):
    return department_service.get_designation(db, designation_id)


@router.post(
    "",
    response_model=DesignationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a designation",
)
def create_designation(
    payload: DesignationCreate,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    return department_service.create_designation(db, payload.model_dump())


@router.patch("/{designation_id}", response_model=DesignationRead, summary="Update")
def update_designation(
    designation_id: int,
    payload: DesignationUpdate,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    return department_service.update_designation(
        db, designation_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/{designation_id}", response_model=MessageResponse, summary="Delete")
def delete_designation(
    designation_id: int,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    department_service.delete_designation(db, designation_id)
    return MessageResponse(message="Designation deleted.")
