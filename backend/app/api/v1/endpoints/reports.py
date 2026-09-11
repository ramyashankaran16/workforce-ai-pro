"""Report generation and export endpoints."""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import RequirePermissions
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.core.pagination import Page, PaginationParams, paginate
from app.models.enums import ReportCategory, ReportStatus
from app.models.report import GeneratedReport, ReportTemplate
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.report import (
    GeneratedReportRead,
    ReportGenerate,
    ReportTemplateCreate,
    ReportTemplateRead,
)
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports & Export"])


@router.get(
    "/templates", response_model=List[ReportTemplateRead], summary="List templates"
)
def list_templates(
    _: User = Depends(RequirePermissions("report:generate")),
    db: Session = Depends(get_db),
):
    return (
        db.execute(
            select(ReportTemplate)
            .where(ReportTemplate.is_active.is_(True))
            .order_by(ReportTemplate.name)
        )
        .scalars()
        .all()
    )


@router.post(
    "/templates",
    response_model=ReportTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a template",
)
def create_template(
    payload: ReportTemplateCreate,
    current_user: User = Depends(RequirePermissions("report:manage")),
    db: Session = Depends(get_db),
):
    return report_service.create_template(
        db, payload.model_dump(), actor_id=current_user.id
    )


@router.post(
    "/generate",
    response_model=GeneratedReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
)
def generate(
    payload: ReportGenerate,
    current_user: User = Depends(RequirePermissions("report:generate")),
    db: Session = Depends(get_db),
):
    """
    Generation is synchronous with a 20,000-row cap. A selection above that is
    refused with a message asking you to narrow the filter, rather than quietly
    timing out. A background worker would be the production answer.

    PDF is the wrong format for wide data -- it truncates to eight columns and
    500 rows. Use Excel or CSV for anything you intend to analyse.
    """
    parameters = payload.model_dump(
        exclude={"category", "file_format", "title", "template_id"}
    )
    return report_service.generate(
        db,
        category=payload.category,
        file_format=payload.file_format,
        title=payload.title,
        parameters={k: v for k, v in parameters.items() if v is not None},
        template_id=payload.template_id,
        actor_id=current_user.id,
    )


@router.get("", response_model=Page[GeneratedReportRead], summary="List reports")
def list_reports(
    params: PaginationParams = Depends(),
    category: Optional[ReportCategory] = Query(None),
    status_filter: Optional[ReportStatus] = Query(None, alias="status"),
    _: User = Depends(RequirePermissions("report:generate")),
    db: Session = Depends(get_db),
):
    stmt = select(GeneratedReport)
    if category:
        stmt = stmt.where(GeneratedReport.category == category)
    if status_filter:
        stmt = stmt.where(GeneratedReport.status == status_filter)
    stmt = stmt.order_by(GeneratedReport.id.desc())

    rows, total = paginate(db, stmt, params)
    return Page[GeneratedReportRead].create(
        [GeneratedReportRead.model_validate(r) for r in rows], total, params
    )


@router.get(
    "/{report_id}/download", summary="Download a report", response_class=FileResponse
)
def download(
    report_id: int,
    _: User = Depends(RequirePermissions("report:generate")),
    db: Session = Depends(get_db),
):
    report = report_service.get_report(db, report_id)
    if report.status != ReportStatus.COMPLETED:
        raise BusinessRuleError(f"This report is {report.status.value}.")
    if not report.file_path or not os.path.exists(report.file_path):
        raise NotFoundError("The generated file is no longer on disk.")

    report.download_count += 1
    db.commit()

    media_types = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
        "pdf": "application/pdf",
    }
    extension = report.file_path.rsplit(".", 1)[-1]
    return FileResponse(
        report.file_path,
        media_type=media_types.get(extension, "application/octet-stream"),
        filename=os.path.basename(report.file_path),
    )


@router.delete("/{report_id}", response_model=MessageResponse, summary="Delete")
def delete_report(
    report_id: int,
    _: User = Depends(RequirePermissions("report:manage")),
    db: Session = Depends(get_db),
):
    report = report_service.get_report(db, report_id)
    if report.file_path and os.path.exists(report.file_path):
        try:
            os.remove(report.file_path)
        except OSError:
            pass
    db.delete(report)
    db.commit()
    return MessageResponse(message="Report deleted.")
