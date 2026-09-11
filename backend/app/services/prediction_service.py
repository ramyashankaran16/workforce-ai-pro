"""Training orchestration, model deployment and prediction persistence."""

import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, NotFoundError
from app.ml import explainer, feature_engineering, predictor, registry
from app.ml.trainer import TrainingConfig, train_model
from app.models.employee import Employee
from app.models.enums import (
    ModelAlgorithm,
    ModelStatus,
    PredictionSource,
    RiskLevel,
)
from app.models.prediction import AttritionPrediction, ModelVersion, PredictionBatch
from app.utils.code_generator import next_sequential_code
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------- training
def train_new_version(
    db: Session,
    name: str,
    algorithm: ModelAlgorithm,
    horizon_days: int = 180,
    voluntary_only: bool = True,
    include_protected: bool = False,
    decision_threshold: float = 0.5,
    hyperparameters: Optional[Dict[str, Any]] = None,
    dataset_id: Optional[int] = None,
    actor_id: Optional[int] = None,
) -> ModelVersion:
    """Build the training frame from live data, fit, evaluate and persist."""
    frame, target, meta = feature_engineering.build_training_frame(
        db,
        horizon_days=horizon_days,
        voluntary_only=voluntary_only,
        include_protected=include_protected,
    )
    if frame.empty:
        raise BusinessRuleError("There are no employee records to train on.")

    numeric, categorical = feature_engineering.feature_columns(frame)

    version = ModelVersion(
        name=name,
        version=registry.next_version_string(db),
        algorithm=algorithm,
        dataset_id=dataset_id,
        status=ModelStatus.TRAINING,
        trained_by_id=actor_id,
        hyperparameters={
            **(hyperparameters or {}),
            "horizon_days": horizon_days,
            "voluntary_only": voluntary_only,
            "include_protected": include_protected,
            "decision_threshold": decision_threshold,
        },
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    try:
        config = TrainingConfig(
            algorithm=algorithm,
            decision_threshold=decision_threshold,
            hyperparameters=hyperparameters or {},
        )
        pipeline, report = train_model(frame, target, numeric, categorical, config)

        path = registry.save_artifact(
            version.id,
            pipeline,
            {
                "feature_columns": numeric + categorical,
                "numeric_features": numeric,
                "categorical_features": categorical,
                "decision_threshold": decision_threshold,
                "training_meta": meta,
            },
        )

        version.artifact_path = path
        version.status = ModelStatus.TRAINED
        version.feature_names = {"numeric": numeric, "categorical": categorical}
        version.feature_importance = report.get("feature_importance")
        version.confusion_matrix = report.get("confusion_matrix")
        version.accuracy = report.get("accuracy")
        version.precision_score = report.get("precision")
        version.recall_score = report.get("recall")
        version.f1_score = report.get("f1")
        version.roc_auc = report.get("roc_auc")
        version.cv_mean_score = report.get("cv_mean_pr_auc")
        version.train_rows = report.get("train_rows")
        version.test_rows = report.get("test_rows")
        version.training_duration_seconds = report.get("training_duration_seconds")
        version.description = (
            f"{meta['rows']} rows, {meta['positives']} attrition cases "
            f"({meta['positive_rate']:.1%}). PR-AUC {report.get('pr_auc')}."
        )
        # keep the full report for the API to surface
        version.hyperparameters = {
            **(version.hyperparameters or {}),
            "evaluation": {
                k: v for k, v in report.items()
                if k not in {"feature_importance", "confusion_matrix"}
            },
            "training_meta": meta,
        }
        db.commit()
        db.refresh(version)
        return version
    except Exception as exc:
        db.rollback()
        version = db.get(ModelVersion, version.id)
        version.status = ModelStatus.FAILED
        version.error_message = str(exc)[:500]
        db.commit()
        logger.exception("Training failed for version %s", version.id)
        raise BusinessRuleError(f"Training failed: {exc}") from exc


# ------------------------------------------------------------------ prediction
def _baseline_frame(db: Session, include_protected: bool = False) -> pd.DataFrame:
    """Population frame used as the neutral reference by the explainer."""
    return feature_engineering.build_feature_frame(
        db, include_protected=include_protected
    )


def predict_for_employee(
    db: Session,
    employee_id: int,
    with_explanation: bool = True,
    source: PredictionSource = PredictionSource.MANUAL,
    persist: bool = True,
) -> AttritionPrediction:
    version = registry.require_deployed(db)

    employee = db.get(Employee, employee_id)
    if employee is None or employee.is_deleted:
        raise NotFoundError("Employee not found.")

    include_protected = bool(
        (version.hyperparameters or {}).get("include_protected", False)
    )
    frame = feature_engineering.build_feature_frame(
        db, employees=[employee], include_protected=include_protected
    )
    if frame.empty:
        raise BusinessRuleError("Could not build features for this employee.")

    result = predictor.predict_one(version, frame)

    top_factors = None
    narrative = None
    if with_explanation:
        baseline = _baseline_frame(db, include_protected)
        detail = explainer.explain(version, frame, baseline)
        top_factors = {"factors": detail["factors"]}
        narrative = detail["narrative"]

    record = AttritionPrediction(
        employee_id=employee.id,
        model_version_id=version.id,
        attrition_probability=result["attrition_probability"],
        will_leave=result["will_leave"],
        risk_level=result["risk_level"],
        confidence=result["confidence"],
        input_features=_serialisable(frame.iloc[0].to_dict()),
        top_factors=top_factors,
        explanation=narrative,
        predicted_at=utcnow(),
        source=source,
    )

    if persist:
        db.add(record)
        _refresh_employee_snapshot(employee, result)
        db.commit()
        db.refresh(record)
    return record


def run_batch(
    db: Session,
    source: PredictionSource = PredictionSource.BATCH,
    actor_id: Optional[int] = None,
) -> PredictionBatch:
    """
    Score every active employee in one pass.

    The frame is built once and the pipeline called once for all rows, rather
    than looping per employee -- at a few thousand staff that is the difference
    between seconds and minutes.
    """
    version = registry.require_deployed(db)
    started = time.perf_counter()

    employees = (
        db.execute(
            select(Employee).where(
                Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None)
            )
        )
        .scalars()
        .all()
    )
    if not employees:
        raise BusinessRuleError("There are no active employees to score.")

    include_protected = bool(
        (version.hyperparameters or {}).get("include_protected", False)
    )
    frame = feature_engineering.build_feature_frame(
        db, employees=employees, include_protected=include_protected
    )
    probabilities, _ = predictor.score_frame(version, frame)

    bundle = predictor.load_bundle(version)
    threshold = float(bundle.get("decision_threshold", 0.5))

    batch = PredictionBatch(
        reference=next_sequential_code(
            db, PredictionBatch, PredictionBatch.reference, "PB", width=5
        ),
        model_version_id=version.id,
        source=source,
        total_records=len(employees),
        triggered_by_id=actor_id,
    )
    db.add(batch)
    db.flush()

    counts = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 0,
              RiskLevel.HIGH: 0, RiskLevel.CRITICAL: 0}

    by_id = {e.id: e for e in employees}
    for position, employee_id in enumerate(frame["employee_id"].tolist()):
        probability = float(probabilities[position])
        level = predictor.band_for(probability)
        counts[level] += 1

        db.add(
            AttritionPrediction(
                employee_id=employee_id,
                model_version_id=version.id,
                batch_id=batch.id,
                attrition_probability=round(probability, 4),
                will_leave=probability >= threshold,
                risk_level=level,
                confidence=round(abs(probability - threshold) * 2, 4),
                predicted_at=utcnow(),
                source=source,
            )
        )

        employee = by_id.get(employee_id)
        if employee is not None:
            _refresh_employee_snapshot(
                employee,
                {"attrition_probability": probability, "risk_level": level},
            )

    batch.high_risk_count = counts[RiskLevel.HIGH] + counts[RiskLevel.CRITICAL]
    batch.medium_risk_count = counts[RiskLevel.MEDIUM]
    batch.low_risk_count = counts[RiskLevel.LOW]
    batch.average_probability = round(float(probabilities.mean()), 4)
    batch.duration_seconds = round(time.perf_counter() - started, 3)

    db.commit()
    db.refresh(batch)
    return batch


def _refresh_employee_snapshot(employee: Employee, result: dict) -> None:
    """
    Keep the denormalised risk fields on `employees` current.

    The dashboard filters high-risk staff constantly; joining the whole
    prediction history for every page load would be wasteful.
    """
    level = result["risk_level"]
    employee.current_risk_score = round(
        float(result["attrition_probability"]) * 100, 2
    )
    employee.current_risk_level = level.value if hasattr(level, "value") else str(level)
    employee.last_risk_evaluated_at = utcnow()


def _serialisable(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if value is None or (isinstance(value, float) and pd.isna(value)):
            out[key] = None
        elif hasattr(value, "item"):
            out[key] = value.item()
        else:
            out[key] = value if isinstance(value, (str, int, float, bool)) else str(value)
    return out


def record_actual_outcome(db: Session, employee_id: int, left: bool) -> int:
    """
    Stamp the real outcome on past predictions so drift can be measured.

    Without this the model can never be evaluated against reality -- only
    against the test split it was born with.
    """
    predictions = (
        db.execute(
            select(AttritionPrediction).where(
                AttritionPrediction.employee_id == employee_id,
                AttritionPrediction.actual_outcome.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for prediction in predictions:
        prediction.actual_outcome = left
        prediction.outcome_recorded_at = utcnow()
    db.commit()
    return len(predictions)
