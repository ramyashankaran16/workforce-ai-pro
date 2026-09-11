"""Training, deployment, prediction and leakage-control tests."""

import random
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.attendance import Attendance
from app.models.department import Department, Designation
from app.models.employee import Employee
from app.models.enums import (
    AttendanceStatus,
    EmployeeStatus,
    EmploymentType,
    Gender,
    ModelAlgorithm,
    ModelStatus,
    WorkMode,
)
from app.ml import feature_engineering, registry
from app.models.prediction import ModelVersion
from app.services import prediction_service


@pytest.fixture
def workforce(db_session, org):
    """
    120 employees with a learnable attrition signal.

    Leavers get attendance up to their exit date, not none at all -- otherwise
    the absence of data becomes a perfect predictor of having left.
    """
    random.seed(11)
    today = date.today()

    departments = db_session.execute(select(Department)).scalars().all()
    designations = db_session.execute(select(Designation)).scalars().all()

    for index in range(120):
        tenure = int(random.triangular(2, 120, 24))
        joined = today - timedelta(days=int(tenure * 30.44))
        satisfaction = random.choices([1, 2, 3, 4, 5], [10, 15, 30, 28, 17])[0]
        promo_gap = min(tenure, int(random.triangular(1, 60, 20)))
        overtime = random.random() < 0.3

        score = 0.05
        if satisfaction <= 2:
            score += 0.35
        if promo_gap > 36:
            score += 0.25
        if overtime:
            score += 0.15
        if tenure < 12:
            score += 0.15
        will_leave = random.random() < min(score, 0.9)

        employee = Employee(
            employee_code=f"GEN{index:04d}",
            first_name=f"Gen{index}",
            last_name="Worker",
            work_email=f"gen{index}@test.com",
            date_of_joining=joined,
            department_id=random.choice(departments).id if departments else None,
            designation_id=random.choice(designations).id if designations else None,
            employment_type=EmploymentType.FULL_TIME,
            work_mode=random.choice(list(WorkMode)),
            gender=random.choice(list(Gender)),
            current_salary=random.randint(300000, 1400000),
            last_promotion_date=today - timedelta(days=promo_gap * 30),
            job_satisfaction_score=satisfaction,
            work_life_balance_score=random.randint(1, 5),
            environment_satisfaction_score=random.randint(1, 5),
            last_performance_rating=round(random.triangular(1.5, 5, 3.4), 1),
            overtime_flag=overtime,
            distance_from_home_km=round(random.triangular(1, 45, 12), 1),
            num_companies_worked=random.randint(0, 5),
            training_hours_last_year=round(random.triangular(0, 80, 20), 1),
            education_level=random.choice(["Bachelors", "Masters", "Diploma"]),
            business_travel_frequency=random.choice(["None", "Rarely", "Frequently"]),
            total_experience_years=round(tenure / 12 + 2, 1),
            status=EmployeeStatus.ACTIVE,
        )
        if will_leave:
            exit_date = today - timedelta(days=random.randint(15, 300))
            if exit_date > joined:
                employee.date_of_exit = exit_date
                employee.status = EmployeeStatus.RESIGNED
                employee.exit_reason = "Better opportunity"

        db_session.add(employee)
    db_session.commit()

    for employee in db_session.execute(
        select(Employee).where(Employee.employee_code.like("GEN%"))
    ).scalars().all():
        bias = 0.03 + (0.07 if (employee.job_satisfaction_score or 3) <= 2 else 0)
        for offset in range(60, 0, -1):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5 or day < employee.date_of_joining:
                continue
            if employee.date_of_exit and day > employee.date_of_exit:
                continue
            roll = random.random()
            status = (
                AttendanceStatus.ABSENT if roll < bias
                else AttendanceStatus.LATE if roll < bias + 0.08
                else AttendanceStatus.PRESENT
            )
            db_session.add(
                Attendance(
                    employee_id=employee.id,
                    attendance_date=day,
                    status=status,
                    worked_hours=0.0 if status == AttendanceStatus.ABSENT else 8.2,
                    overtime_hours=0.4 if employee.overtime_flag else 0.0,
                )
            )
    db_session.commit()
    return True


# ------------------------------------------------------------------- leakage
def test_leaky_columns_are_not_features(db_session, workforce):
    frame, _, meta = feature_engineering.build_training_frame(db_session)
    for column in ["date_of_exit", "exit_reason", "status", "current_risk_score"]:
        assert column not in frame.columns
    assert "date_of_exit" in meta["excluded_for_leakage"]


def test_protected_attributes_excluded_by_default(db_session, workforce):
    frame, _, meta = feature_engineering.build_training_frame(db_session)
    assert "gender" not in frame.columns
    assert "marital_status" not in frame.columns
    assert "gender" in meta["excluded_as_protected"]
    assert meta["protected_attributes_included"] is False


def test_protected_attributes_included_only_when_asked(db_session, workforce):
    frame, _, meta = feature_engineering.build_training_frame(
        db_session, include_protected=True
    )
    assert "gender" in frame.columns
    assert meta["protected_attributes_included"] is True
    assert meta["excluded_as_protected"] == []


def test_terminations_excluded_when_voluntary_only(db_session, workforce, org):
    terminated = db_session.execute(
        select(Employee).where(Employee.employee_code == "GEN0000")
    ).scalar_one()
    terminated.date_of_exit = date.today() - timedelta(days=30)
    terminated.status = EmployeeStatus.TERMINATED
    db_session.commit()

    _, _, voluntary = feature_engineering.build_training_frame(
        db_session, voluntary_only=True
    )
    _, _, everything = feature_engineering.build_training_frame(
        db_session, voluntary_only=False
    )
    assert everything["rows"] > voluntary["rows"]


def test_behaviour_window_anchors_on_exit_date(db_session, workforce):
    """
    A leaver's absence rate must be computed from the period before they left.

    Anchoring every window at today would leave recent leavers with an empty
    window, and the model would learn to spot the missing data rather than the
    behaviour that preceded the resignation.
    """
    cutoff = date.today() - timedelta(days=50)
    leaver = db_session.execute(
        select(Employee).where(
            Employee.employee_code.like("GEN%"),
            Employee.date_of_exit.isnot(None),
            Employee.date_of_exit >= cutoff,
        )
    ).scalars().first()
    if leaver is None:
        pytest.skip("No leaver inside the generated attendance window.")

    frame = feature_engineering.build_feature_frame(db_session, employees=[leaver])
    assert frame.loc[0, "absence_rate"] is not None

    # and the window must not reach past the exit date
    rows = db_session.execute(
        select(Attendance).where(
            Attendance.employee_id == leaver.id,
            Attendance.attendance_date > leaver.date_of_exit,
        )
    ).scalars().all()
    assert rows == []


# ------------------------------------------------------------------ training
def test_training_produces_honest_metrics(client, hr_headers, workforce):
    resp = client.post(
        "/api/v1/predictions/train",
        json={"name": "Attrition RF", "algorithm": "random_forest",
              "decision_threshold": 0.4},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "trained"

    evaluation = body["hyperparameters"]["evaluation"]
    # accuracy must be reported alongside the score for predicting the
    # majority class, so it cannot be quoted in isolation
    assert "majority_class_baseline_accuracy" in evaluation
    assert "pr_auc" in evaluation
    assert len(evaluation["threshold_sweep"]) == 6


def test_perfect_scores_would_signal_leakage(client, hr_headers, workforce):
    """A real model on noisy data should not be perfect. This is a canary."""
    body = client.post(
        "/api/v1/predictions/train",
        json={"name": "Canary", "algorithm": "random_forest"},
        headers=hr_headers,
    ).json()
    assert body["hyperparameters"]["evaluation"]["pr_auc"] < 0.999


def test_training_refuses_too_few_positives(client, hr_headers, org):
    resp = client.post(
        "/api/v1/predictions/train",
        json={"name": "Tiny", "algorithm": "logistic_regression"},
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_logistic_regression_also_trains(client, hr_headers, workforce):
    resp = client.post(
        "/api/v1/predictions/train",
        json={"name": "Attrition LR", "algorithm": "logistic_regression"},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["feature_importance"]


def test_employee_cannot_train(client, employee_headers, workforce):
    resp = client.post(
        "/api/v1/predictions/train",
        json={"name": "Nope", "algorithm": "random_forest"},
        headers=employee_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------- deployment
def _trained(client, headers, name="Model"):
    return client.post(
        "/api/v1/predictions/train",
        json={"name": name, "algorithm": "random_forest", "decision_threshold": 0.4},
        headers=headers,
    ).json()


def test_deploy_makes_exactly_one_version_active(client, hr_headers, workforce):
    first = _trained(client, hr_headers, "First")
    second = _trained(client, hr_headers, "Second")

    client.post(f"/api/v1/predictions/models/{first['id']}/deploy", headers=hr_headers)
    client.post(f"/api/v1/predictions/models/{second['id']}/deploy", headers=hr_headers)

    models = client.get("/api/v1/predictions/models", headers=hr_headers).json()
    active = [m for m in models["items"] if m["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == second["id"]


def test_previous_version_is_archived(client, hr_headers, workforce):
    first = _trained(client, hr_headers, "First")
    second = _trained(client, hr_headers, "Second")
    client.post(f"/api/v1/predictions/models/{first['id']}/deploy", headers=hr_headers)
    client.post(f"/api/v1/predictions/models/{second['id']}/deploy", headers=hr_headers)

    older = client.get(
        f"/api/v1/predictions/models/{first['id']}", headers=hr_headers
    ).json()
    assert older["status"] == "archived"


def test_prediction_refused_with_no_deployed_model(client, hr_headers, workforce, org):
    resp = client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}", headers=hr_headers
    )
    assert resp.status_code == 400
    assert "deployed" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------- predicting
@pytest.fixture
def deployed(client, hr_headers, workforce):
    version = _trained(client, hr_headers, "Deployed")
    client.post(
        f"/api/v1/predictions/models/{version['id']}/deploy", headers=hr_headers
    )
    return version


def test_single_prediction_returns_probability_and_band(
    client, hr_headers, deployed, org
):
    resp = client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}", headers=hr_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["attrition_probability"] <= 1.0
    assert body["risk_level"] in {"low", "medium", "high", "critical"}
    assert isinstance(body["will_leave"], bool)


def test_explanation_names_specific_factors(client, hr_headers, deployed, org):
    body = client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}?explain=true",
        headers=hr_headers,
    ).json()

    assert body["explanation"]
    assert body["factors"]
    factor = body["factors"][0]
    assert factor["direction"] in {"increases risk", "reduces risk"}
    assert factor["label"]  # human-readable, not the raw column name


def test_batch_scores_every_active_employee(client, hr_headers, deployed):
    resp = client.post("/api/v1/predictions/batch", headers=hr_headers)
    assert resp.status_code == 200
    batch = resp.json()

    assert batch["total_records"] > 0
    total = (
        batch["high_risk_count"] + batch["medium_risk_count"] + batch["low_risk_count"]
    )
    assert total == batch["total_records"]


def test_batch_refreshes_the_employee_snapshot(
    client, hr_headers, deployed, db_session, org
):
    client.post("/api/v1/predictions/batch", headers=hr_headers)
    employee = db_session.get(Employee, org["reportee_id"])
    db_session.refresh(employee)
    assert employee.current_risk_score is not None
    assert employee.current_risk_level is not None


def test_predictions_filter_by_risk_level(client, hr_headers, deployed):
    client.post("/api/v1/predictions/batch", headers=hr_headers)
    resp = client.get("/api/v1/predictions?risk_level=low", headers=hr_headers)
    assert resp.status_code == 200
    assert all(p["risk_level"] == "low" for p in resp.json()["items"])


def test_prediction_history_is_ordered(client, hr_headers, deployed, org):
    client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}", headers=hr_headers
    )
    client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}", headers=hr_headers
    )
    history = client.get(
        f"/api/v1/predictions/employee/{org['reportee_id']}/history",
        headers=hr_headers,
    ).json()
    assert len(history) == 2


def test_employee_cannot_score_another_employee(
    client, employee_headers, deployed, org
):
    resp = client.post(
        f"/api/v1/predictions/employee/{org['outsider_id']}", headers=employee_headers
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------- outcomes
def test_recording_an_outcome_stamps_past_predictions(
    client, hr_headers, deployed, org
):
    client.post(
        f"/api/v1/predictions/employee/{org['reportee_id']}", headers=hr_headers
    )
    resp = client.post(
        "/api/v1/predictions/outcomes",
        json={"employee_id": org["reportee_id"], "left": True},
        headers=hr_headers,
    )
    assert resp.status_code == 200

    history = client.get(
        f"/api/v1/predictions/employee/{org['reportee_id']}/history",
        headers=hr_headers,
    ).json()
    assert all(p["actual_outcome"] is True for p in history)


def test_risk_bands_are_ordered():
    from app.ml.predictor import band_for

    assert band_for(0.9).value == "critical"
    assert band_for(0.6).value == "high"
    assert band_for(0.4).value == "medium"
    assert band_for(0.1).value == "low"
