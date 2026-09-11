"""
Model training and evaluation.

Accuracy is not reported as the headline metric. With attrition around 15%, a
model that predicts "nobody leaves" scores 85% accuracy and is worthless. The
metrics that matter here are recall (what fraction of leavers we catch),
precision (how many flagged people were actually going to leave) and PR-AUC,
which is the right summary statistic for an imbalanced positive class.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

from app.ml.preprocessing import build_preprocessor, expanded_feature_names
from app.models.enums import ModelAlgorithm

logger = logging.getLogger(__name__)

MIN_ROWS = 20
MIN_POSITIVES = 5


@dataclass
class TrainingConfig:
    algorithm: ModelAlgorithm = ModelAlgorithm.RANDOM_FOREST
    test_size: float = 0.25
    random_state: int = 42
    # class_weight="balanced" tells the estimator to weight the rare class up,
    # rather than resampling the data.
    balance_classes: bool = True
    decision_threshold: float = 0.5
    hyperparameters: Dict[str, Any] = field(default_factory=dict)


def build_estimator(config: TrainingConfig):
    weight = "balanced" if config.balance_classes else None
    params = dict(config.hyperparameters)

    if config.algorithm == ModelAlgorithm.LOGISTIC_REGRESSION:
        return LogisticRegression(
            max_iter=params.pop("max_iter", 1000),
            class_weight=weight,
            random_state=config.random_state,
            **params,
        )
    if config.algorithm == ModelAlgorithm.DECISION_TREE:
        return DecisionTreeClassifier(
            max_depth=params.pop("max_depth", 6),
            class_weight=weight,
            random_state=config.random_state,
            **params,
        )
    if config.algorithm == ModelAlgorithm.GRADIENT_BOOSTING:
        # GradientBoosting has no class_weight; imbalance is handled by the
        # decision threshold instead.
        return GradientBoostingClassifier(
            n_estimators=params.pop("n_estimators", 200),
            max_depth=params.pop("max_depth", 3),
            random_state=config.random_state,
            **params,
        )
    return RandomForestClassifier(
        n_estimators=params.pop("n_estimators", 300),
        max_depth=params.pop("max_depth", None),
        min_samples_leaf=params.pop("min_samples_leaf", 2),
        class_weight=weight,
        random_state=config.random_state,
        n_jobs=-1,
        **params,
    )


def threshold_sweep(y_true, probabilities) -> List[Dict[str, float]]:
    """
    Precision and recall at several thresholds.

    0.5 is an arbitrary default. For retention, a false positive costs one
    awkward conversation and a false negative costs an employee, so the right
    operating point is usually lower.
    """
    out = []
    for threshold in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        predicted = (probabilities >= threshold).astype(int)
        out.append(
            {
                "threshold": threshold,
                "precision": round(
                    float(precision_score(y_true, predicted, zero_division=0)), 4
                ),
                "recall": round(
                    float(recall_score(y_true, predicted, zero_division=0)), 4
                ),
                "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 4),
                "flagged": int(predicted.sum()),
            }
        )
    return out


def train_model(
    frame: pd.DataFrame,
    target: pd.Series,
    numeric_features: List[str],
    categorical_features: List[str],
    config: Optional[TrainingConfig] = None,
) -> Tuple[Pipeline, Dict[str, Any]]:
    """Fit a pipeline and return it with an evaluation report."""
    config = config or TrainingConfig()
    started = time.perf_counter()

    if len(frame) < MIN_ROWS:
        raise ValueError(
            f"Need at least {MIN_ROWS} rows to train; got {len(frame)}."
        )
    positives = int(target.sum())
    if positives < MIN_POSITIVES:
        raise ValueError(
            f"Need at least {MIN_POSITIVES} attrition cases to train; got {positives}. "
            "A model cannot learn a pattern from too few examples of it."
        )
    if positives == len(target):
        raise ValueError("Every row is an attrition case; there is nothing to separate.")

    features = frame[numeric_features + categorical_features]

    X_train, X_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=config.test_size,
        random_state=config.random_state,
        stratify=target if positives >= 2 else None,
    )

    preprocessor = build_preprocessor(numeric_features, categorical_features)
    pipeline = Pipeline(
        steps=[("preprocess", preprocessor), ("model", build_estimator(config))]
    )
    pipeline.fit(X_train, y_train)

    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predicted = (probabilities >= config.decision_threshold).astype(int)

    matrix = confusion_matrix(y_test, predicted, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()

    # The score a model gets for predicting the majority class every time.
    majority_baseline = round(float(max(1 - y_test.mean(), y_test.mean())), 4)

    try:
        roc = round(float(roc_auc_score(y_test, probabilities)), 4)
    except ValueError:
        roc = None

    report: Dict[str, Any] = {
        "precision": round(float(precision_score(y_test, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, predicted, zero_division=0)), 4),
        "roc_auc": roc,
        "pr_auc": round(float(average_precision_score(y_test, probabilities)), 4),
        "accuracy": round(float((predicted == y_test).mean()), 4),
        "majority_class_baseline_accuracy": majority_baseline,
        "confusion_matrix": {
            "true_negative": int(tn), "false_positive": int(fp),
            "false_negative": int(fn), "true_positive": int(tp),
        },
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "positive_rate": round(float(target.mean()), 4),
        "decision_threshold": config.decision_threshold,
        "threshold_sweep": threshold_sweep(y_test, probabilities),
    }

    # cross-validation, only when every fold can hold a positive
    folds = min(5, positives)
    if folds >= 2:
        try:
            scores = cross_val_score(
                pipeline,
                features,
                target,
                cv=StratifiedKFold(n_splits=folds, shuffle=True,
                                   random_state=config.random_state),
                scoring="average_precision",
            )
            report["cv_folds"] = folds
            report["cv_mean_pr_auc"] = round(float(scores.mean()), 4)
            report["cv_std_pr_auc"] = round(float(scores.std()), 4)
        except ValueError as exc:
            logger.warning("Cross-validation skipped: %s", exc)

    report["feature_importance"] = compute_importance(
        pipeline, numeric_features, categorical_features
    )
    report["training_duration_seconds"] = round(time.perf_counter() - started, 3)
    return pipeline, report


def compute_importance(
    pipeline: Pipeline, numeric_features: List[str], categorical_features: List[str]
) -> Dict[str, float]:
    """
    Global feature importance.

    Impurity-based for trees and absolute coefficients for linear models. This
    describes the model overall -- it does not explain any individual
    prediction, which is what the explainer module is for.
    """
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]
    names = expanded_feature_names(preprocessor, numeric_features, categorical_features)

    if hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    elif hasattr(model, "coef_"):
        values = np.abs(model.coef_[0])
    else:
        return {}

    pairs = sorted(zip(names, values), key=lambda kv: kv[1], reverse=True)
    return {name: round(float(value), 5) for name, value in pairs[:25]}
