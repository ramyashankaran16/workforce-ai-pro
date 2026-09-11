"""Report schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import ReportCategory, ReportFormat, ReportStatus
from app.schemas.common import ORMBase


class ReportTemplateCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=150)
    description: Optional[str] = None
    category: ReportCategory = ReportCategory.CUSTOM
    default_format: ReportFormat = ReportFormat.PDF
    columns: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    grouping: Optional[Dict[str, Any]] = None
    sort_order: Optional[Dict[str, Any]] = None
    is_scheduled: bool = False
    cron_expression: Optional[str] = None
    recipients: Optional[Dict[str, Any]] = None


class ReportTemplateRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    category: ReportCategory
    default_format: ReportFormat
    filters: Optional[Dict[str, Any]] = None
    is_scheduled: bool
    cron_expression: Optional[str] = None
    is_system_template: bool
    is_active: bool


class ReportGenerate(BaseModel):
    category: ReportCategory
    file_format: ReportFormat = ReportFormat.EXCEL
    title: Optional[str] = None
    template_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    department_id: Optional[int] = None
    year: Optional[int] = Field(None, ge=2000, le=2100)
    run_id: Optional[int] = None
    active_only: bool = True


class GeneratedReportRead(ORMBase):
    id: int
    reference: str
    title: str
    category: ReportCategory
    file_format: ReportFormat
    file_size: Optional[int] = None
    row_count: int
    status: ReportStatus
    error_message: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    download_count: int
    created_at: datetime
