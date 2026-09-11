"""Department endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.pagination import Page, PaginationParams, paginate
from app.models.department import Department
from app.models.employee import Employee
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.department import (
    DepartmentCreate,
    DepartmentDetail,
    DepartmentNode,
    DepartmentRead,
    DepartmentUpdate,
)
from app.services import department_service

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=Page[DepartmentRead], summary="List departments")
def list_departments(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Match code or name"),
    is_active: Optional[bool] = Query(None),
    parent_id: Optional[int] = Query(None),
    _: User = Depends(RequirePermissions("department:read")),
    db: Session = Depends(get_db),
):
    stmt = select(Department).where(Department.is_deleted.is_(False))
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Department.name.ilike(pattern), Department.code.ilike(pattern))
        )
    if is_active is not None:
        stmt = stmt.where(Department.is_active.is_(is_active))
    if parent_id is not None:
        stmt = stmt.where(Department.parent_id == parent_id)

    stmt = stmt.order_by(Department.name)
    rows, total = paginate(db, stmt, params)
    return Page[DepartmentRead].create(
        [DepartmentRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/tree",
    response_model=List[DepartmentNode],
    summary="Nested department hierarchy with headcounts",
)
def department_tree(
    _: User = Depends(RequirePermissions("department:read")),
    db: Session = Depends(get_db),
):
    return department_service.build_tree(db)


@router.get("/{department_id}", response_model=DepartmentDetail, summary="Get a department")
def get_department(
    department_id: int,
    _: User = Depends(RequirePermissions("department:read")),
    db: Session = Depends(get_db),
):
    dept = department_service.get_department(db, department_id)
    counts = department_service.headcount_map(db)

    head_name = None
    if dept.head_employee_id:
        head = db.get(Employee, dept.head_employee_id)
        head_name = head.full_name if head else None

    parent_name = None
    if dept.parent_id:
        parent = db.get(Department, dept.parent_id)
        parent_name = parent.name if parent else None

    payload = {c.name: getattr(dept, c.name) for c in dept.__table__.columns}
    payload.update(
        {
            "headcount": counts.get(dept.id, 0),
            "head_name": head_name,
            "parent_name": parent_name,
        }
    )
    return payload


@router.post(
    "",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
def create_department(
    payload: DepartmentCreate,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    return department_service.create_department(db, payload.model_dump())


@router.patch(
    "/{department_id}", response_model=DepartmentRead, summary="Update a department"
)
def update_department(
    department_id: int,
    payload: DepartmentUpdate,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    return department_service.update_department(
        db, department_id, payload.model_dump(exclude_unset=True)
    )


@router.delete(
    "/{department_id}", response_model=MessageResponse, summary="Delete a department"
)
def delete_department(
    department_id: int,
    _: User = Depends(RequirePermissions("department:manage")),
    db: Session = Depends(get_db),
):
    department_service.delete_department(db, department_id)
    return MessageResponse(message="Department deleted.")
