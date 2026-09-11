"""Reusable column mixins shared by every ORM model."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds automatic created_at / updated_at tracking."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """Adds soft-delete support so historical records are never lost."""

    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
