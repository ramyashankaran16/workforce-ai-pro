"""Uploaded HR datasets used to train the attrition model."""

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
from app.models.enums import ColumnDataType, DatasetStatus, enum_col
from app.models.mixins import SoftDeleteMixin, TimestampMixin
from app.models.types import JSONType


class Dataset(Base, TimestampMixin, SoftDeleteMixin):
    """A CSV/Excel upload plus its profiling summary."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_format: Mapped[str] = mapped_column(String(20), default="csv", nullable=False)

    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_columns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_column: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    positive_class_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    missing_value_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[DatasetStatus] = mapped_column(
        enum_col(DatasetStatus), default=DatasetStatus.UPLOADED, nullable=False, index=True
    )
    validation_errors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    statistics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    columns: Mapped[List["DatasetColumn"]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    model_versions: Mapped[List["ModelVersion"]] = relationship(back_populates="dataset")

    def __repr__(self) -> str:
        return f"<Dataset {self.name} rows={self.total_rows}>"


class DatasetColumn(Base):
    """Per-column profile: type, nulls, cardinality, basic statistics."""

    __tablename__ = "dataset_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    data_type: Mapped[ColumnDataType] = mapped_column(enum_col(ColumnDataType), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    null_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mean_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    std_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    top_categories: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)

    is_feature: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_target: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    dataset: Mapped["Dataset"] = relationship(back_populates="columns")

    def __repr__(self) -> str:
        return f"<DatasetColumn {self.name}:{self.data_type}>"
