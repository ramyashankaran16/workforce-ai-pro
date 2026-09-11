"""Document schemas."""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import DocumentStatus, DocumentVisibility
from app.schemas.common import ORMBase


class DocumentCategoryRead(ORMBase):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_mandatory: bool
    requires_expiry: bool
    allowed_extensions: str
    max_size_mb: int
    is_active: bool


class DocumentCategoryCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=80)
    description: Optional[str] = None
    is_mandatory: bool = False
    requires_expiry: bool = False
    allowed_extensions: str = "pdf,jpg,jpeg,png,docx"
    max_size_mb: int = Field(10, ge=1, le=100)


class DocumentRead(ORMBase):
    id: int
    employee_id: int
    category_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    file_name: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    version: int
    status: DocumentStatus
    visibility: DocumentVisibility
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    verified_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime


class DocumentVerify(BaseModel):
    approve: bool
    reason: Optional[str] = Field(None, description="Required when rejecting.")


class ExpiringDocument(BaseModel):
    document_id: int
    title: str
    employee_id: int
    employee_code: str
    employee_name: str
    expiry_date: date
    days_remaining: int
    already_expired: bool


class ComplianceReport(BaseModel):
    employee_id: int
    employee_code: str
    employee_name: str
    missing_mandatory: List[str] = []
    is_compliant: bool
