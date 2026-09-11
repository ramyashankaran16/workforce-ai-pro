"""Payroll endpoints."""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import (
    RequirePermissions,
    get_current_employee,
    get_current_user,
)
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.employee import Employee
from app.models.enums import PayrollStatus
from app.models.payroll import PayrollRun, Payslip, SalaryStructure
from app.models.user import User
from app.schemas.payroll import (
    AdjustmentCreate,
    PayrollRunCreate,
    PayrollRunRead,
    PayrollSummary,
    PayslipDetail,
    PayslipRead,
    ProcessResult,
    SalaryStructureCreate,
    SalaryStructureRead,
)
from app.services import employee_service, payroll_service
from app.utils.pdf_export import generate_payslip_pdf

router = APIRouter(prefix="/payroll", tags=["Payroll"])


# ------------------------------------------------------------ salary structure
@router.get(
    "/structures/{employee_id}",
    response_model=List[SalaryStructureRead],
    summary="Salary structure history",
)
def structure_history(
    employee_id: int,
    _: User = Depends(RequirePermissions("payroll:manage")),
    db: Session = Depends(get_db),
):
    """Effective-dated history, newest first. Past structures are never overwritten."""
    rows = (
        db.execute(
            select(SalaryStructure)
            .where(SalaryStructure.employee_id == employee_id)
            .order_by(SalaryStructure.effective_from.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for row in rows:
        totals = payroll_service.structure_totals(row)
        out.append(
            {**{c.name: getattr(row, c.name) for c in row.__table__.columns}, **totals}
        )
    return out


@router.post(
    "/structures",
    response_model=SalaryStructureRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an effective-dated salary structure",
)
def create_structure(
    payload: SalaryStructureCreate,
    current_user: User = Depends(RequirePermissions("payroll:manage")),
    db: Session = Depends(get_db),
):
    """Closes the previous structure the day before this one takes effect."""
    structure = payroll_service.create_structure(
        db, payload.model_dump(), actor_id=current_user.id
    )
    totals = payroll_service.structure_totals(structure)
    return {
        **{c.name: getattr(structure, c.name) for c in structure.__table__.columns},
        **totals,
    }


# ---------------------------------------------------------------- payroll runs
@router.get("/runs", response_model=Page[PayrollRunRead], summary="List payroll runs")
def list_runs(
    params: PaginationParams = Depends(),
    year: Optional[int] = Query(None),
    status_filter: Optional[PayrollStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("payroll:read_all")),
    db: Session = Depends(get_db),
):
    stmt = select(PayrollRun)
    if year:
        stmt = stmt.where(PayrollRun.year == year)
    if status_filter:
        stmt = stmt.where(PayrollRun.status == status_filter)
    stmt = stmt.order_by(PayrollRun.year.desc(), PayrollRun.month.desc())

    rows, total = paginate(db, stmt, params)
    return Page[PayrollRunRead].create(
        [PayrollRunRead.model_validate(r) for r in rows], total, params
    )


@router.post(
    "/runs",
    response_model=PayrollRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payroll run for a month",
)
def create_run(
    payload: PayrollRunCreate,
    _: User = Depends(RequirePermissions("payroll:process")),
    db: Session = Depends(get_db),
):
    return payroll_service.create_run(
        db, payload.month, payload.year, payload.notes
    )


@router.get("/runs/{run_id}", response_model=PayrollRunRead, summary="Get a run")
def get_run(
    run_id: int,
    _: User = Depends(RequirePermissions("payroll:read_all")),
    db: Session = Depends(get_db),
):
    return payroll_service.get_run(db, run_id)


@router.get(
    "/runs/{run_id}/summary",
    response_model=PayrollSummary,
    summary="Aggregate figures for a run",
)
def run_summary(
    run_id: int,
    _: User = Depends(RequirePermissions("payroll:read_all")),
    db: Session = Depends(get_db),
):
    return payroll_service.run_summary(db, run_id)


@router.post(
    "/runs/{run_id}/process",
    response_model=ProcessResult,
    summary="Generate payslips from attendance and leave",
)
def process_run(
    run_id: int,
    current_user: User = Depends(RequirePermissions("payroll:process")),
    db: Session = Depends(get_db),
):
    """
    Loss of pay is derived from absent days and approved unpaid leave in the
    period. Employees with no salary structure in force are skipped and listed
    in the response rather than silently omitted.
    """
    return payroll_service.process_run(db, run_id, actor_id=current_user.id)


@router.post(
    "/runs/{run_id}/approve", response_model=PayrollRunRead, summary="Lock the run"
)
def approve_run(
    run_id: int,
    current_user: User = Depends(RequirePermissions("payroll:process")),
    db: Session = Depends(get_db),
):
    return payroll_service.approve_run(db, run_id, actor_id=current_user.id)


@router.post(
    "/runs/{run_id}/mark-paid",
    response_model=PayrollRunRead,
    summary="Record that the run has been disbursed",
)
def mark_paid(
    run_id: int,
    _: User = Depends(RequirePermissions("payroll:process")),
    db: Session = Depends(get_db),
):
    """After this, payslips in the run are immutable."""
    return payroll_service.mark_paid(db, run_id)


@router.get(
    "/runs/{run_id}/payslips",
    response_model=Page[PayslipRead],
    summary="Payslips in a run",
)
def run_payslips(
    run_id: int,
    params: PaginationParams = Depends(),
    _: User = Depends(RequirePermissions("payroll:read_all")),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Payslip)
        .where(Payslip.payroll_run_id == run_id)
        .order_by(Payslip.slip_number)
    )
    rows, total = paginate(db, stmt, params)
    return Page[PayslipRead].create(
        [PayslipRead.model_validate(r) for r in rows], total, params
    )


# --------------------------------------------------------------------- payslips
@router.get(
    "/payslips/me", response_model=Page[PayslipRead], summary="Own payslips"
)
def my_payslips(
    params: PaginationParams = Depends(),
    year: Optional[int] = Query(None),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    stmt = select(Payslip).where(Payslip.employee_id == employee.id)
    if year:
        stmt = stmt.join(PayrollRun).where(PayrollRun.year == year)
    stmt = stmt.order_by(Payslip.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[PayslipRead].create(
        [PayslipRead.model_validate(r) for r in rows], total, params
    )


def _load_payslip_for_caller(
    db: Session, payslip_id: int, current_user: User
) -> Payslip:
    payslip = db.get(Payslip, payslip_id)
    if payslip is None:
        raise NotFoundError("Payslip not found.")

    role = (current_user.role_name or "").lower()
    if role in {"admin", "hr"}:
        return payslip

    profile = employee_service.get_by_user(db, current_user.id)
    if profile is None or payslip.employee_id != profile.id:
        raise PermissionDeniedError("You can only view your own payslips.")
    return payslip


@router.get(
    "/payslips/{payslip_id}",
    response_model=PayslipDetail,
    summary="Payslip with line items",
)
def get_payslip(
    payslip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Employees may read only their own; HR and admin may read any."""
    payslip = _load_payslip_for_caller(db, payslip_id, current_user)
    return payroll_service.build_payslip_detail(db, payslip)


@router.get(
    "/payslips/{payslip_id}/pdf",
    summary="Download the payslip as a PDF",
    response_class=FileResponse,
)
def download_payslip(
    payslip_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payslip = _load_payslip_for_caller(db, payslip_id, current_user)
    detail = payroll_service.build_payslip_detail(db, payslip)

    detail["line_items"] = [
        {
            "component_name": item.component_name,
            "component_type": item.component_type.value,
            "amount": item.amount,
        }
        for item in detail["line_items"]
    ]

    output_dir = os.path.join(settings.UPLOAD_DIR, "payslips")
    path = generate_payslip_pdf(detail, output_dir, settings.APP_NAME)
    return FileResponse(
        path, media_type="application/pdf", filename=f"{payslip.slip_number}.pdf"
    )


@router.post(
    "/payslips/{payslip_id}/adjustments",
    response_model=PayslipDetail,
    summary="Add an arrears or recovery line",
)
def add_adjustment(
    payslip_id: int,
    payload: AdjustmentCreate,
    _: User = Depends(RequirePermissions("payroll:process")),
    db: Session = Depends(get_db),
):
    """
    Rejected once the run is approved or paid. A correction found after payment
    belongs on the next run, so the payslip continues to match what was
    actually disbursed.
    """
    payslip = payroll_service.add_adjustment(db, payslip_id, payload.model_dump())
    return payroll_service.build_payslip_detail(db, payslip)
