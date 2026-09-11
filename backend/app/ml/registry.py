"""Model artifact persistence and version bookkeeping."""

import logging
import os
from typing import Optional, Tuple

import joblib
from sklearn.pipeline import Pipeline
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BusinessRuleError, NotFoundError
from app.models.enums import ModelStatus
from app.models.prediction import ModelVersion
from app.utils.date_utils import utcnow

logger = logging.getLogger(__name__)

# In-process cache so batch scoring does not reload the artifact per employee.
_cache: dict = {}


def artifact_path(version_id: int) -> str:
    os.makedirs(settings.ML_MODEL_DIR, exist_ok=True)
    return os.path.join(settings.ML_MODEL_DIR, f"model_v{version_id}.joblib")


def save_artifact(version_id: int, pipeline: Pipeline, payload: dict) -> str:
    """
    Persist the fitted pipeline together with everything needed to reproduce a
    prediction: the feature list, the threshold, and the training config.
    """
    path = artifact_path(version_id)
    joblib.dump({"pipeline": pipeline, **payload}, path)
    _cache.pop(version_id, None)
    return path


def load_artifact(version_id: int, path: str) -> dict:
    if version_id in _cache:
        return _cache[version_id]
    if not os.path.exists(path):
        raise NotFoundError(
            f"Model artifact is missing at {path}. Retrain this version."
        )
    bundle = joblib.load(path)
    _cache[version_id] = bundle
    return bundle


def next_version_string(db: Session) -> str:
    count = db.execute(select(ModelVersion)).scalars().all()
    return f"1.{len(count)}"


def deployed_model(db: Session) -> Optional[ModelVersion]:
    return db.execute(
        select(ModelVersion).where(
            ModelVersion.is_active.is_(True),
            ModelVersion.status == ModelStatus.DEPLOYED,
        )
    ).scalars().first()


def require_deployed(db: Session) -> ModelVersion:
    model = deployed_model(db)
    if model is None:
        raise BusinessRuleError(
            "No model is currently deployed. Train one, then deploy it."
        )
    return model


def deploy(db: Session, version_id: int) -> ModelVersion:
    """Exactly one version may be active; deploying stands the others down."""
    version = db.get(ModelVersion, version_id)
    if version is None:
        raise NotFoundError("Model version not found.")
    if version.status not in {ModelStatus.TRAINED, ModelStatus.DEPLOYED,
                              ModelStatus.ARCHIVED}:
        raise BusinessRuleError(
            f"Cannot deploy a version that is {version.status.value}."
        )
    if not version.artifact_path or not os.path.exists(version.artifact_path):
        raise BusinessRuleError("The artifact for this version is missing on disk.")

    for other in db.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    ).scalars().all():
        other.is_active = False
        if other.id != version_id:
            other.status = ModelStatus.ARCHIVED

    version.is_active = True
    version.status = ModelStatus.DEPLOYED
    version.deployed_at = utcnow()
    db.commit()
    db.refresh(version)
    logger.info("Deployed model version %s (id=%s)", version.version, version.id)
    return version
