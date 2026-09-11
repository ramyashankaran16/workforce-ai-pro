"""Report templates and generated report files."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ReportCategory, ReportFormat, ReportStatus, enum_col
from app.models.mixins import TimestampMixin
from app.models.types import JSONType


class ReportTemplate(Base, TimestampMixin):
    """A saved report definition that can be run on demand or on a schedule."""

    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[ReportCategory] = mapped_column(
        enum_col(ReportCategory), default=ReportCategory.CUSTOM, nullable=False, index=True
    )
    default_format: Mapped[ReportFormat] = mapped_column(
        enum_col(ReportFormat), default=ReportFormat.PDF, nullable=False
    )

    columns: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    filters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    grouping: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    sort_order: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cron_expression: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    recipients: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    is_system_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    generated_reports: Mapped[List["GeneratedReport"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ReportTemplate {self.name}>"


class GeneratedReport(Base, TimestampMixin):
    """One produced report file."""

    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ReportCategory] = mapped_column(
        enum_col(ReportCategory), default=ReportCategory.CUSTOM, nullable=False
    )
    file_format: Mapped[ReportFormat] = mapped_column(
        enum_col(ReportFormat), default=ReportFormat.PDF, nullable=False
    )

    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    status: Mapped[ReportStatus] = mapped_column(
        enum_col(ReportStatus), default=ReportStatus.QUEUED, nullable=False, index=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generation_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    generated_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    template: Mapped[Optional["ReportTemplate"]] = relationship(
        back_populates="generated_reports"
    )

    def __repr__(self) -> str:
        return f"<GeneratedReport {self.reference} {self.status}>"
