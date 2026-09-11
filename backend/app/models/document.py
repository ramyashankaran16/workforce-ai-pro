"""Employee document vault."""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import DocumentStatus, DocumentVisibility, enum_col
from app.models.mixins import SoftDeleteMixin, TimestampMixin


class DocumentCategory(Base, TimestampMixin):
    """Grouping such as ID Proof, Certificate, Offer Letter."""

    __tablename__ = "document_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allowed_extensions: Mapped[str] = mapped_column(
        String(200), default="pdf,jpg,jpeg,png,docx", nullable=False
    )
    max_size_mb: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    documents: Mapped[List["Document"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<DocumentCategory {self.code}>"


class Document(Base, TimestampMixin, SoftDeleteMixin):
    """An uploaded file belonging to an employee."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("document_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_col(DocumentStatus), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    visibility: Mapped[DocumentVisibility] = mapped_column(
        enum_col(DocumentVisibility), default=DocumentVisibility.HR_ONLY, nullable=False
    )

    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship(
        back_populates="documents", foreign_keys=[employee_id]
    )
    category: Mapped[Optional["DocumentCategory"]] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document {self.title} emp={self.employee_id}>"
