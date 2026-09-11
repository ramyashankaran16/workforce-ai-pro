"""Preprocessing pipeline: imputation, scaling and categorical encoding."""

from typing import List

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def build_preprocessor(
    numeric_features: List[str], categorical_features: List[str]
) -> ColumnTransformer:
    """
    Fitted once during training and persisted alongside the model.

    handle_unknown="ignore" matters: a job role that did not appear in training
    encodes as all-zeros instead of raising at prediction time. New designations
    get created all the time, and a prediction endpoint that crashes on one is
    worse than one that treats it as unseen.
    """
    numeric_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ],
        remainder="drop",
    )


def expanded_feature_names(
    preprocessor: ColumnTransformer,
    numeric_features: List[str],
    categorical_features: List[str],
) -> List[str]:
    """Column names after one-hot expansion, for importance reporting."""
    names = list(numeric_features)
    if categorical_features:
        encoder = preprocessor.named_transformers_["categorical"].named_steps["encode"]
        names.extend(encoder.get_feature_names_out(categorical_features).tolist())
    return names


def align_frame(frame: pd.DataFrame, expected: List[str]) -> pd.DataFrame:
    """
    Reindex an inference frame to the training column set.

    Missing columns are added as NA and imputed downstream; extra columns are
    dropped. Without this, a schema change silently shifts every column.
    """
    aligned = frame.copy()
    for column in expected:
        if column not in aligned.columns:
            aligned[column] = pd.NA
    return aligned[expected]
