"""CSV ingestion, column profiling and schema validation."""

import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError, ValidationError
from app.models.dataset import Dataset, DatasetColumn
from app.models.enums import ColumnDataType, DatasetStatus
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

MAX_PREVIEW_ROWS = 50
HIGH_CARDINALITY_RATIO = 0.5
HIGH_MISSING_RATIO = 0.4
# A column with at most this many distinct values is categorical whatever the
# row count. The ratio test alone misfires on small files: three departments
# across five rows is a ratio of 0.6, which would read as free text.
MAX_CATEGORICAL_LEVELS = 25


def _infer_type(series: pd.Series) -> ColumnDataType:
    if pd.api.types.is_bool_dtype(series):
        return ColumnDataType.BOOLEAN
    if pd.api.types.is_numeric_dtype(series):
        return ColumnDataType.NUMERIC
    if pd.api.types.is_datetime64_any_dtype(series):
        return ColumnDataType.DATETIME

    non_null = series.dropna()
    if non_null.empty:
        return ColumnDataType.TEXT

    distinct = non_null.nunique()
    if distinct <= MAX_CATEGORICAL_LEVELS:
        return ColumnDataType.CATEGORICAL
    # Otherwise fall back to the ratio: few distinct values relative to length
    # still reads as a category rather than free text.
    if distinct / len(non_null) < HIGH_CARDINALITY_RATIO:
        return ColumnDataType.CATEGORICAL
    return ColumnDataType.TEXT


def read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    try:
        if lowered.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(content))
        return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    except Exception as exc:
        raise ValidationError(f"Could not parse the file: {exc}")


def profile_frame(frame: pd.DataFrame) -> Tuple[List[dict], dict]:
    """Per-column statistics plus a dataset-level summary."""
    columns = []
    for position, name in enumerate(frame.columns):
        series = frame[name]
        data_type = _infer_type(series)

        entry: Dict[str, Any] = {
            "name": str(name),
            "data_type": data_type,
            "position": position,
            "null_count": int(series.isna().sum()),
            "unique_count": int(series.nunique(dropna=True)),
            "min_value": None,
            "max_value": None,
            "mean_value": None,
            "std_value": None,
            "top_categories": None,
        }

        if data_type == ColumnDataType.NUMERIC and series.notna().any():
            entry.update(
                {
                    "min_value": float(series.min()),
                    "max_value": float(series.max()),
                    "mean_value": round(float(series.mean()), 4),
                    "std_value": round(float(series.std(ddof=0) or 0), 4),
                }
            )
        elif data_type in {ColumnDataType.CATEGORICAL, ColumnDataType.BOOLEAN}:
            counts = series.value_counts(dropna=True).head(10)
            entry["top_categories"] = {
                str(key): int(value) for key, value in counts.items()
            }

        columns.append(entry)

    summary = {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "total_missing": int(frame.isna().sum().sum()),
        "duplicate_rows": int(frame.duplicated().sum()),
        "memory_kb": round(frame.memory_usage(deep=True).sum() / 1024, 1),
    }
    return columns, summary


def create_dataset(
    db: Session,
    content: bytes,
    filename: str,
    name: str,
    description: Optional[str] = None,
    target_column: Optional[str] = None,
    uploaded_by_id: Optional[int] = None,
) -> Dataset:
    frame = read_dataframe(content, filename)
    if frame.empty:
        raise ValidationError("The file contains no rows.")

    if target_column and target_column not in frame.columns:
        raise ValidationError(
            f"Target column '{target_column}' is not present. "
            f"Available: {', '.join(map(str, frame.columns[:15]))}"
        )

    os.makedirs(settings.DATASET_DIR, exist_ok=True)
    safe_name = os.path.basename(filename).replace(" ", "_")
    path = os.path.join(settings.DATASET_DIR, f"{utcnow():%Y%m%d%H%M%S}_{safe_name}")
    with open(path, "wb") as handle:
        handle.write(content)

    columns, summary = profile_frame(frame)

    positive_ratio = None
    if target_column:
        target = frame[target_column]
        mapped = _coerce_binary(target)
        if mapped is not None:
            positive_ratio = round(float(mapped.mean()), 4)

    dataset = Dataset(
        name=name,
        description=description,
        file_name=safe_name,
        file_path=path,
        file_size=len(content),
        file_format="xlsx" if filename.lower().endswith((".xlsx", ".xls")) else "csv",
        total_rows=summary["rows"],
        total_columns=summary["columns"],
        target_column=target_column,
        positive_class_ratio=positive_ratio,
        missing_value_count=summary["total_missing"],
        duplicate_row_count=summary["duplicate_rows"],
        status=DatasetStatus.UPLOADED,
        statistics=summary,
        uploaded_by_id=uploaded_by_id,
    )
    db.add(dataset)
    db.flush()

    for entry in columns:
        db.add(
            DatasetColumn(
                dataset_id=dataset.id,
                is_target=(entry["name"] == target_column),
                is_feature=(entry["name"] != target_column),
                **entry,
            )
        )

    db.commit()
    db.refresh(dataset)
    return dataset


def _coerce_binary(series: pd.Series) -> Optional[pd.Series]:
    """Map a target column to 0/1, accepting Yes/No, True/False and 1/0."""
    if pd.api.types.is_numeric_dtype(series):
        values = set(series.dropna().unique().tolist())
        if values.issubset({0, 1}):
            return series.fillna(0).astype(int)
        return None

    lowered = series.astype(str).str.strip().str.lower()
    mapping = {"yes": 1, "no": 0, "true": 1, "false": 0, "1": 1, "0": 0,
               "y": 1, "n": 0, "left": 1, "stayed": 0}
    if set(lowered.dropna().unique()).issubset(set(mapping)):
        return lowered.map(mapping).fillna(0).astype(int)
    return None


def validate_dataset(db: Session, dataset_id: int) -> dict:
    """
    Quality checks that would otherwise surface as a confusing training error.

    Returns a report rather than raising, so the user can see everything wrong
    at once instead of fixing one issue per attempt.
    """
    dataset = get_dataset(db, dataset_id)
    frame = read_dataframe(open(dataset.file_path, "rb").read(), dataset.file_name)

    errors: List[str] = []
    warnings: List[str] = []

    if len(frame) < 50:
        warnings.append(
            f"Only {len(frame)} rows. A model trained on this will not generalise."
        )

    if dataset.target_column:
        target = frame[dataset.target_column]
        mapped = _coerce_binary(target)
        if mapped is None:
            errors.append(
                f"Target column '{dataset.target_column}' is not binary. "
                "Expected Yes/No, True/False or 1/0."
            )
        else:
            positive_rate = float(mapped.mean())
            if positive_rate == 0 or positive_rate == 1:
                errors.append("The target column has only one class.")
            elif positive_rate < 0.05:
                warnings.append(
                    f"Only {positive_rate:.1%} positive cases. Expect low precision "
                    "and treat accuracy as meaningless."
                )
    else:
        warnings.append("No target column set; this dataset cannot be used for training.")

    for column in frame.columns:
        missing_ratio = frame[column].isna().mean()
        if missing_ratio > HIGH_MISSING_RATIO:
            warnings.append(
                f"'{column}' is {missing_ratio:.0%} empty and may add noise."
            )
        if frame[column].nunique(dropna=True) <= 1:
            warnings.append(f"'{column}' has a single value and carries no signal.")

    duplicates = int(frame.duplicated().sum())
    if duplicates:
        warnings.append(f"{duplicates} duplicate row(s) found.")

    report = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
    }

    dataset.status = DatasetStatus.VALIDATED if not errors else DatasetStatus.FAILED
    dataset.validation_errors = report
    dataset.processed_at = utcnow()
    db.commit()
    return report


def get_dataset(db: Session, dataset_id: int) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.is_deleted:
        raise NotFoundError("Dataset not found.")
    return dataset


def preview(db: Session, dataset_id: int, rows: int = 10) -> dict:
    dataset = get_dataset(db, dataset_id)
    if not os.path.exists(dataset.file_path):
        raise NotFoundError("The uploaded file is no longer on disk.")

    frame = read_dataframe(open(dataset.file_path, "rb").read(), dataset.file_name)
    limited = frame.head(min(rows, MAX_PREVIEW_ROWS))
    return {
        "columns": [str(c) for c in frame.columns],
        "rows": limited.replace({np.nan: None}).to_dict(orient="records"),
        "total_rows": int(len(frame)),
    }


def soft_delete(db: Session, dataset_id: int) -> None:
    dataset = get_dataset(db, dataset_id)
    linked = dataset.model_versions
    if linked:
        raise BusinessRuleError(
            f"{len(linked)} model version(s) were trained from this dataset."
        )
    dataset.is_deleted = True
    db.commit()
