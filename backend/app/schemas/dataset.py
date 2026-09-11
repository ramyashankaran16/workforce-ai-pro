"""Dataset schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.enums import ColumnDataType, DatasetStatus
from app.schemas.common import ORMBase


class DatasetColumnRead(ORMBase):
    id: int
    name: str
    data_type: ColumnDataType
    position: int
    null_count: int
    unique_count: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_value: Optional[float] = None
    top_categories: Optional[Dict[str, Any]] = None
    is_feature: bool
    is_target: bool


class DatasetRead(ORMBase):
    id: int
    name: str
    description: Optional[str] = None
    file_name: str
    file_size: Optional[int] = None
    file_format: str
    total_rows: int
    total_columns: int
    target_column: Optional[str] = None
    positive_class_ratio: Optional[float] = None
    missing_value_count: int
    duplicate_row_count: int
    status: DatasetStatus
    created_at: datetime


class DatasetDetail(DatasetRead):
    statistics: Optional[Dict[str, Any]] = None
    validation_errors: Optional[Dict[str, Any]] = None
    columns: List[DatasetColumnRead] = []


class DatasetPreview(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int


class ValidationReport(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    rows: int
    columns: int
