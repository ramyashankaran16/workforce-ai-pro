"""Employee endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import RequirePermissions, get_current_user
from app.core.exceptions import BusinessRuleError, ValidationError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee, EmployeeHistory
from app.models.enums import EmployeeStatus, EmploymentType, WorkMode
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.employee import (
    BulkImportResult,
    EmployeeCreate,
    EmployeeCreatedResponse,
    EmployeeDetail,
    EmployeeExit,
    EmployeeHistoryRead,
    EmployeeRead,
    EmployeeUpdate,
    OrgNode,
    TeamMember,
)
from app.services import employee_service

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=Page[EmployeeRead], summary="List employees (scoped)")
def list_employees(
    params: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Match name, code or work email"),
    department_id: Optional[int] = Query(None),
    designation_id: Optional[int] = Query(None),
    manager_id: Optional[int] = Query(None),
    status_filter: Optional[EmployeeStatus] = Query(None, alias="status"),
    employment_type: Optional[EmploymentType] = Query(None),
    work_mode: Optional[WorkMode] = Query(None),
    current_user: User = Depends(RequirePermissions("employee:read")),
    db: Session = Depends(get_db),
):
    """
    Rows are scoped by role: admin and HR see everyone, managers see themselves
    plus their direct reportees, employees see only their own record.
    """
    stmt = select(Employee).where(Employee.is_deleted.is_(False))

    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(pattern),
                Employee.last_name.ilike(pattern),
                Employee.employee_code.ilike(pattern),
                Employee.work_email.ilike(pattern),
            )
        )
    if department_id is not None:
        stmt = stmt.where(Employee.department_id == department_id)
    if designation_id is not None:
        stmt = stmt.where(Employee.designation_id == designation_id)
    if manager_id is not None:
        stmt = stmt.where(Employee.manager_id == manager_id)
    if status_filter:
        stmt = stmt.where(Employee.status == status_filter)
    if employment_type:
        stmt = stmt.where(Employee.employment_type == employment_type)
    if work_mode:
        stmt = stmt.where(Employee.work_mode == work_mode)

    stmt = employee_service.scope_query(db, stmt, current_user)
    stmt = stmt.order_by(Employee.employee_code)

    rows, total = paginate(db, stmt, params)
    items = [
        EmployeeRead.model_validate(
            {**{c.name: getattr(r, c.name) for c in r.__table__.columns},
             "full_name": r.full_name}
        )
        for r in rows
    ]
    return Page[EmployeeRead].create(items, total, params)


@router.get("/me", response_model=EmployeeDetail, summary="Own employee profile")
def my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = employee_service.get_by_user(db, current_user.id)
    if profile is None:
        raise BusinessRuleError("No employee profile is linked to your account.")
    return employee_service.build_detail(db, profile)


@router.get("/org-chart", response_model=List[OrgNode], summary="Reporting tree")
def org_chart(
    root_id: Optional[int] = Query(None, description="Subtree root; omit for top level"),
    max_depth: int = Query(6, ge=1, le=10),
    _: User = Depends(RequirePermissions("employee:read")),
    db: Session = Depends(get_db),
):
    return employee_service.org_tree(db, root_id, max_depth)


@router.get("/{employee_id}", response_model=EmployeeDetail, summary="Get an employee")
def get_employee(
    employee_id: int,
    current_user: User = Depends(RequirePermissions("employee:read")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)
    return employee_service.build_detail(db, employee)


@router.get(
    "/{employee_id}/team",
    response_model=List[TeamMember],
    summary="Direct reportees",
)
def get_team(
    employee_id: int,
    current_user: User = Depends(RequirePermissions("employee:read")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    reportees = (
        db.execute(
            select(Employee)
            .where(
                Employee.manager_id == employee_id,
                Employee.is_deleted.is_(False),
            )
            .order_by(Employee.first_name)
        )
        .scalars()
        .all()
    )
    return [
        TeamMember.model_validate(
            {
                "id": r.id,
                "employee_code": r.employee_code,
                "full_name": r.full_name,
                "work_email": r.work_email,
                "designation_id": r.designation_id,
                "status": r.status,
                "reportee_count": employee_service.reportee_count(db, r.id),
            }
        )
        for r in reportees
    ]


@router.get(
    "/{employee_id}/history",
    response_model=List[EmployeeHistoryRead],
    summary="Change history",
)
def get_history(
    employee_id: int,
    current_user: User = Depends(RequirePermissions("employee:read")),
    db: Session = Depends(get_db),
):
    employee = employee_service.get_employee(db, employee_id)
    employee_service.assert_can_access(db, current_user, employee)

    return (
        db.execute(
            select(EmployeeHistory)
            .where(EmployeeHistory.employee_id == employee_id)
            .order_by(EmployeeHistory.effective_date.desc(), EmployeeHistory.id.desc())
        )
        .scalars()
        .all()
    )


@router.post(
    "",
    response_model=EmployeeCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee",
)
def create_employee(
    payload: EmployeeCreate,
    current_user: User = Depends(RequirePermissions("employee:create")),
    db: Session = Depends(get_db),
):
    employee, user_created, temp_password = employee_service.create_employee(
        db, payload.model_dump(), actor=current_user
    )
    return EmployeeCreatedResponse(
        employee=EmployeeRead.model_validate(
            {**{c.name: getattr(employee, c.name) for c in employee.__table__.columns},
             "full_name": employee.full_name}
        ),
        user_created=user_created,
        temporary_password=temp_password,
    )


@router.patch(
    "/{employee_id}", response_model=EmployeeDetail, summary="Update an employee"
)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    current_user: User = Depends(RequirePermissions("employee:update")),
    db: Session = Depends(get_db),
):
    """Material changes (department, designation, manager, salary, status) are
    written to employee_history automatically."""
    employee = employee_service.update_employee(
        db, employee_id, payload.model_dump(exclude_unset=True), actor=current_user
    )
    return employee_service.build_detail(db, employee)


@router.post(
    "/{employee_id}/exit", response_model=EmployeeDetail, summary="Record an exit"
)
def record_exit(
    employee_id: int,
    payload: EmployeeExit,
    current_user: User = Depends(RequirePermissions("employee:update")),
    db: Session = Depends(get_db),
):
    employee = employee_service.record_exit(
        db, employee_id, payload.model_dump(), actor=current_user
    )
    return employee_service.build_detail(db, employee)


@router.delete(
    "/{employee_id}", response_model=MessageResponse, summary="Soft delete"
)
def delete_employee(
    employee_id: int,
    _: User = Depends(RequirePermissions("employee:delete")),
    db: Session = Depends(get_db),
):
    employee_service.soft_delete(db, employee_id)
    return MessageResponse(message="Employee record deleted.")


@router.post(
    "/import",
    response_model=BulkImportResult,
    summary="Bulk import from CSV",
)
async def import_employees(
    file: UploadFile = File(..., description="CSV with a header row"),
    current_user: User = Depends(RequirePermissions("employee:create")),
    db: Session = Depends(get_db),
):
    """
    Expected columns: first_name, last_name, work_email, phone, date_of_joining
    (YYYY-MM-DD), department_code, designation_code, manager_code,
    employment_type, work_mode, current_salary.

    Rows are processed independently -- a bad row is reported and skipped
    rather than aborting the import.
    """
    if not (file.filename or "").lower().endswith(".csv"):
        raise ValidationError("Only .csv files are accepted.")

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise ValidationError(f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB.")

    return employee_service.import_csv(db, content, actor=current_user)
