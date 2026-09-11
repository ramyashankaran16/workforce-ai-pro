"""
Report generation.

Generation is synchronous here, with a row cap, because a background worker
would need a queue this project does not run. The cap is the honest mitigation:
a report that would exceed it is refused with a message telling the user to
narrow the filter, rather than quietly timing out the request.
"""

import csv
import io
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.attendance import Attendance
from app.models.audit import AuditLog
from app.models.department import Department
from app.models.employee import Employee
from app.models.enums import (
    ReportCategory,
    ReportFormat,
    ReportStatus,
)
from app.models.leave import LeaveRequest, LeaveType
from app.models.payroll import PayrollRun, Payslip
from app.models.prediction import AttritionPrediction
from app.models.report import GeneratedReport, ReportTemplate
from app.utils.code_generator import next_sequential_code
from app.utils.date_utils import utcnow
from app.utils.excel_export import build_workbook

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(settings.UPLOAD_DIR, "reports")
MAX_ROWS = 20_000
RETENTION_DAYS = 30


def _json_safe(params: dict) -> dict:
    """
    Make the parameter dict storable in a JSON column.

    date and datetime are not JSON-serialisable, and `parameters` is persisted
    on the report row so a run can be reproduced later. They go in as ISO
    strings and come back out through _as_date().
    """
    out = {}
    for key, value in (params or {}).items():
        if isinstance(value, (date, datetime)):
            out[key] = value.isoformat()
        elif hasattr(value, "value"):
            out[key] = value.value
        else:
            out[key] = value
    return out


def _as_date(value, fallback: Optional[date] = None) -> Optional[date]:
    """Accept a date, an ISO string, or nothing."""
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return fallback


# --------------------------------------------------------------- data sources
def _employees(db: Session, params: dict) -> List[dict]:
    stmt = select(Employee).where(Employee.is_deleted.is_(False))
    if params.get("department_id"):
        stmt = stmt.where(Employee.department_id == params["department_id"])
    if params.get("active_only", True):
        stmt = stmt.where(Employee.date_of_exit.is_(None))

    departments = {
        d.id: d.name for d in db.execute(select(Department)).scalars().all()
    }
    return [
        {
            "employee_code": e.employee_code,
            "full_name": e.full_name,
            "work_email": e.work_email,
            "department": departments.get(e.department_id),
            "employment_type": e.employment_type,
            "work_mode": e.work_mode,
            "status": e.status,
            "date_of_joining": e.date_of_joining,
            "date_of_exit": e.date_of_exit,
            "tenure_months": e.tenure_months,
            "risk_level": e.current_risk_level,
            "risk_score": e.current_risk_score,
        }
        for e in db.execute(stmt.order_by(Employee.employee_code)).scalars().all()
    ]


def _attendance(db: Session, params: dict) -> List[dict]:
    start = _as_date(params.get("start_date"), date.today() - timedelta(days=30))
    end = _as_date(params.get("end_date"), date.today())

    rows = db.execute(
        select(Attendance, Employee)
        .join(Employee, Employee.id == Attendance.employee_id)
        .where(
            Attendance.attendance_date >= start,
            Attendance.attendance_date <= end,
            *(
                [Employee.department_id == params["department_id"]]
                if params.get("department_id")
                else []
            ),
        )
        .order_by(Attendance.attendance_date.desc())
    ).all()

    return [
        {
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "date": record.attendance_date,
            "status": record.status,
            "check_in": record.check_in,
            "check_out": record.check_out,
            "worked_hours": record.worked_hours,
            "overtime_hours": record.overtime_hours,
            "late_minutes": record.late_minutes,
        }
        for record, employee in rows
    ]


def _leave(db: Session, params: dict) -> List[dict]:
    start = _as_date(params.get("start_date"), date.today() - timedelta(days=90))
    end = _as_date(params.get("end_date"), date.today())

    rows = db.execute(
        select(LeaveRequest, Employee, LeaveType)
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
        .where(LeaveRequest.start_date >= start, LeaveRequest.start_date <= end)
        .order_by(LeaveRequest.start_date.desc())
    ).all()

    return [
        {
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "leave_type": leave_type.name,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "total_days": request.total_days,
            "status": request.status,
            "reason": request.reason,
        }
        for request, employee, leave_type in rows
    ]


def _payroll(db: Session, params: dict) -> List[dict]:
    stmt = select(Payslip, Employee, PayrollRun).join(
        Employee, Employee.id == Payslip.employee_id
    ).join(PayrollRun, PayrollRun.id == Payslip.payroll_run_id)

    if params.get("run_id"):
        stmt = stmt.where(Payslip.payroll_run_id == params["run_id"])
    elif params.get("year"):
        stmt = stmt.where(PayrollRun.year == params["year"])

    rows = db.execute(stmt.order_by(Payslip.slip_number)).all()
    return [
        {
            "slip_number": payslip.slip_number,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "period": f"{run.month:02d}/{run.year}",
            "working_days": payslip.working_days,
            "present_days": payslip.present_days,
            "loss_of_pay_days": payslip.unpaid_leave_days,
            "gross_earnings": float(payslip.gross_earnings),
            "total_deductions": float(payslip.total_deductions),
            "net_pay": float(payslip.net_pay),
            "status": payslip.status,
        }
        for payslip, employee, run in rows
    ]


def _attrition(db: Session, params: dict) -> List[dict]:
    rows = db.execute(
        select(AttritionPrediction, Employee)
        .join(Employee, Employee.id == AttritionPrediction.employee_id)
        .order_by(AttritionPrediction.attrition_probability.desc())
    ).all()

    departments = {
        d.id: d.name for d in db.execute(select(Department)).scalars().all()
    }
    return [
        {
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "department": departments.get(employee.department_id),
            "attrition_probability": prediction.attrition_probability,
            "risk_level": prediction.risk_level,
            "will_leave": prediction.will_leave,
            "predicted_at": prediction.predicted_at,
            "explanation": prediction.explanation,
        }
        for prediction, employee in rows
    ]


def _audit(db: Session, params: dict) -> List[dict]:
    start = _as_date(params.get("start_date"), date.today() - timedelta(days=30))
    rows = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.created_at >= datetime.combine(start, datetime.min.time()))
            .order_by(AuditLog.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "timestamp": row.created_at,
            "user_email": row.user_email,
            "user_role": row.user_role,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "description": row.description,
            "successful": row.is_successful,
            "ip_address": row.ip_address,
        }
        for row in rows
    ]


def _headcount(db: Session, params: dict) -> List[dict]:
    rows = db.execute(
        select(
            Department.name,
            func.count(Employee.id),
            func.avg(Employee.current_risk_score),
        )
        .join(Employee, Employee.department_id == Department.id)
        .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
        .group_by(Department.name)
    ).all()
    return [
        {
            "department": name,
            "headcount": int(count),
            "average_risk_score": round(float(average), 2) if average else None,
        }
        for name, count, average in rows
    ]


SOURCES: Dict[ReportCategory, Callable[[Session, dict], List[dict]]] = {
    ReportCategory.ATTENDANCE: _attendance,
    ReportCategory.LEAVE: _leave,
    ReportCategory.PAYROLL: _payroll,
    ReportCategory.ATTRITION: _attrition,
    ReportCategory.AUDIT: _audit,
    ReportCategory.HEADCOUNT: _headcount,
    ReportCategory.CUSTOM: _employees,
    ReportCategory.PERFORMANCE: _employees,
}


# ----------------------------------------------------------------- generation
def _write_csv(rows: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        if not rows:
            handle.write("No data for this selection.\n")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: (v.value if hasattr(v, "value") else v)
                    for k, v in row.items()
                }
            )


def _write_json(rows: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def default(value):
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, default=default, indent=2)


def _write_pdf(rows: List[dict], path: str, title: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    document = SimpleDocTemplate(
        path, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Heading1"]), Spacer(1, 6)]

    if not rows:
        story.append(Paragraph("No data for this selection.", styles["Normal"]))
        document.build(story)
        return

    # PDF is a fixed-width medium: too many columns become unreadable
    headers = list(rows[0].keys())[:8]
    data = [[h.replace("_", " ").title() for h in headers]]
    for row in rows[:500]:
        data.append(
            [
                str(
                    row.get(h).value if hasattr(row.get(h), "value") else row.get(h, "")
                )[:28]
                for h in headers
            ]
        )

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    story.append(table)

    if len(rows) > 500:
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"Showing the first 500 of {len(rows)} rows. "
                "Export to Excel or CSV for the full set.",
                styles["Normal"],
            )
        )

    document.build(story)


def generate(
    db: Session,
    category: ReportCategory,
    file_format: ReportFormat,
    title: Optional[str] = None,
    parameters: Optional[dict] = None,
    template_id: Optional[int] = None,
    actor_id: Optional[int] = None,
) -> GeneratedReport:
    started = time.perf_counter()
    parameters = parameters or {}

    # Swagger's example body sends 0 for optional ids. Treat 0 as "not set"
    # rather than letting it become a foreign key that does not exist.
    if not template_id:
        template_id = None
    elif db.get(ReportTemplate, template_id) is None:
        raise NotFoundError(f"Report template {template_id} does not exist.")

    for key in ("department_id", "run_id"):
        if parameters.get(key) in (0, "0"):
            parameters.pop(key)

    reference = next_sequential_code(
        db, GeneratedReport, GeneratedReport.reference, "RPT", width=5
    )
    report = GeneratedReport(
        template_id=template_id,
        reference=reference,
        title=title or f"{category.value.title()} report",
        category=category,
        file_format=file_format,
        parameters=_json_safe(parameters),
        status=ReportStatus.GENERATING,
        generated_by_id=actor_id,
        expires_at=utcnow() + timedelta(days=RETENTION_DAYS),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    try:
        source = SOURCES.get(category, _employees)
        rows = source(db, parameters)

        if len(rows) > MAX_ROWS:
            raise BusinessRuleError(
                f"This selection returns {len(rows):,} rows; the limit is "
                f"{MAX_ROWS:,}. Narrow the date range or filter by department."
            )

        extension = {
            ReportFormat.CSV: "csv",
            ReportFormat.EXCEL: "xlsx",
            ReportFormat.JSON: "json",
            ReportFormat.PDF: "pdf",
        }[file_format]
        path = os.path.join(REPORT_DIR, f"{reference}.{extension}")

        if file_format == ReportFormat.CSV:
            _write_csv(rows, path)
        elif file_format == ReportFormat.JSON:
            _write_json(rows, path)
        elif file_format == ReportFormat.EXCEL:
            build_workbook({category.value.title(): rows}, path)
        else:
            _write_pdf(rows, path, report.title)

        report.file_path = path
        report.file_size = os.path.getsize(path)
        report.row_count = len(rows)
        report.status = ReportStatus.COMPLETED
        report.completed_at = utcnow()
        report.generation_time_seconds = round(time.perf_counter() - started, 3)
        db.commit()
        db.refresh(report)
        return report
    except Exception as exc:
        db.rollback()
        failed = db.get(GeneratedReport, report.id)
        if failed is not None:
            failed.status = ReportStatus.FAILED
            failed.error_message = str(exc)[:500]
            db.commit()
        logger.exception("Report %s failed", reference)
        raise


def get_report(db: Session, report_id: int) -> GeneratedReport:
    report = db.get(GeneratedReport, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    return report


def create_template(db: Session, data: dict, actor_id: Optional[int] = None) -> ReportTemplate:
    template = ReportTemplate(**data, created_by_id=actor_id)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def purge_expired(db: Session) -> int:
    rows = (
        db.execute(
            select(GeneratedReport).where(
                GeneratedReport.expires_at.isnot(None),
                GeneratedReport.expires_at < utcnow(),
            )
        )
        .scalars()
        .all()
    )
    for report in rows:
        if report.file_path and os.path.exists(report.file_path):
            try:
                os.remove(report.file_path)
            except OSError:
                pass
        db.delete(report)
    db.commit()
    return len(rows)