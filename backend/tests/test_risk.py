"""Risk scoring, alerting, forecasting and intervention tests."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.employee import Employee
from app.models.enums import (
    AlertStatus,
    InterventionStatus,
    InterventionType,
    RiskLevel,
    RuleOperator,
    RuleTargetMetric,
)
from app.models.risk import RiskAlert, RiskScore
from app.services import risk_service


# ------------------------------------------------------------------ sub-scores
def test_band_thresholds_are_ordered():
    assert risk_service.band_for(80).value == "critical"
    assert risk_service.band_for(60).value == "high"
    assert risk_service.band_for(40).value == "medium"
    assert risk_service.band_for(10).value == "low"


def test_weights_sum_to_one():
    assert round(sum(risk_service.WEIGHTS.values()), 6) == 1.0


def test_low_engagement_raises_the_sub_score(db_session, org):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 1
    employee.work_life_balance_score = 1
    employee.environment_satisfaction_score = 2
    db_session.commit()

    score, _ = risk_service._engagement(employee)
    assert score > 75


def test_high_engagement_lowers_the_sub_score(db_session, org):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 5
    employee.work_life_balance_score = 5
    employee.environment_satisfaction_score = 5
    db_session.commit()

    score, _ = risk_service._engagement(employee)
    assert score == 0


def test_pay_below_band_raises_compensation_risk(db_session, org):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.last_hike_date = date.today() - timedelta(days=900)
    db_session.commit()

    low, low_note = risk_service._compensation(employee, percentile=10)
    high, _ = risk_service._compensation(employee, percentile=90)
    assert low > high
    assert "bottom quartile" in low_note


def test_short_tenure_raises_risk(db_session, org):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.date_of_joining = date.today() - timedelta(days=120)
    db_session.commit()
    score, note = risk_service._tenure(employee)
    assert score == 70.0
    assert "months in role" in note


def test_high_performers_flagged_as_retention_targets(db_session, org):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.last_performance_rating = 4.8
    db_session.commit()
    score, note = risk_service._performance(employee)
    assert "retention target" in note


# --------------------------------------------------------------------- scoring
def test_evaluate_produces_a_score_with_factors(client, hr_headers, org, db_session):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 2
    employee.work_life_balance_score = 2
    db_session.commit()

    resp = client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    assert resp.status_code == 200
    assert resp.json()["evaluated"] == 1

    detail = client.get(
        f"/api/v1/risk/employee/{org['reportee_id']}", headers=hr_headers
    ).json()
    assert 0 <= detail["overall_score"] <= 100
    assert detail["factors"]
    assert detail["summary"]


def test_ml_weight_redistributed_when_no_model(client, hr_headers, org, db_session):
    """Without a deployed model the ML weight must not be scored as zero."""
    client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    detail = client.get(
        f"/api/v1/risk/employee/{org['reportee_id']}", headers=hr_headers
    ).json()

    assert detail["ml_probability_score"] is None
    breakdown = detail["breakdown"]
    assert breakdown["ml_available"] is False
    # weights used must exclude the ML component and still normalise
    assert "ml_probability_score" not in breakdown["weights"]
    assert breakdown["weight_total_used"] < 1.0


def test_second_evaluation_records_a_trend(client, hr_headers, org, db_session):
    client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 1
    employee.work_life_balance_score = 1
    employee.environment_satisfaction_score = 1
    db_session.commit()

    client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    history = client.get(
        f"/api/v1/risk/employee/{org['reportee_id']}/history", headers=hr_headers
    ).json()
    assert len(history) == 2
    assert history[0]["trend"] in {"worsening", "stable", "improving"}
    assert history[0]["previous_score"] is not None


def test_evaluate_all_returns_band_counts(client, hr_headers, org):
    resp = client.post("/api/v1/risk/evaluate", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["evaluated"] == 4
    assert body["critical"] + body["high"] + body["medium"] + body["low"] == 4


def test_evaluation_updates_the_employee_snapshot(client, hr_headers, org, db_session):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    employee = db_session.get(Employee, org["reportee_id"])
    db_session.refresh(employee)
    assert employee.current_risk_score is not None
    assert employee.current_risk_level is not None


def test_heatmap_groups_by_department(client, hr_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    resp = client.get("/api/v1/risk/heatmap", headers=hr_headers)
    assert resp.status_code == 200
    names = {d["department_name"] for d in resp.json()}
    assert "Engineering" in names


def test_employee_cannot_evaluate_risk(client, employee_headers, org):
    resp = client.post("/api/v1/risk/evaluate", headers=employee_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------- alerts
def test_alert_lifecycle(client, hr_headers, org, db_session):
    client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    score = db_session.execute(
        select(RiskScore).where(RiskScore.employee_id == org["reportee_id"])
    ).scalars().first()
    employee = db_session.get(Employee, org["reportee_id"])
    alert = risk_service.raise_alert(db_session, employee, score)

    ack = client.post(
        f"/api/v1/risk/alerts/{alert.id}/acknowledge", headers=hr_headers
    )
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    resolved = client.post(
        f"/api/v1/risk/alerts/{alert.id}/resolve",
        json={"notes": "Spoke with the employee; salary review scheduled."},
        headers=hr_headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_resolved_alert_cannot_be_resolved_again(client, hr_headers, org, db_session):
    client.post(
        f"/api/v1/risk/evaluate?employee_id={org['reportee_id']}", headers=hr_headers
    )
    score = db_session.execute(
        select(RiskScore).where(RiskScore.employee_id == org["reportee_id"])
    ).scalars().first()
    employee = db_session.get(Employee, org["reportee_id"])
    alert = risk_service.raise_alert(db_session, employee, score)

    client.post(
        f"/api/v1/risk/alerts/{alert.id}/resolve",
        json={"notes": "Handled"},
        headers=hr_headers,
    )
    second = client.post(
        f"/api/v1/risk/alerts/{alert.id}/resolve",
        json={"notes": "Again"},
        headers=hr_headers,
    )
    assert second.status_code == 400


# ----------------------------------------------------------------- alert rules
def _rule(client, headers, **overrides):
    payload = {
        "name": "High risk score",
        "metric": "risk_score",
        "operator": "gte",
        "threshold_value": 1.0,
        "scope": "organisation",
        "priority": "high",
        "cooldown_hours": 24,
        "notify_roles": {"roles": ["hr"]},
    }
    payload.update(overrides)
    return client.post("/api/v1/alert-rules", json=payload, headers=headers)


def test_rule_creation_and_evaluation(client, hr_headers, admin_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)

    created = _rule(client, admin_headers)
    assert created.status_code == 201

    resp = client.post("/api/v1/alert-rules/evaluate", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rules_evaluated"] == 1
    assert body["triggers"] > 0
    assert body["alerts_created"] == body["triggers"]


def test_cooldown_suppresses_a_repeat_run(client, hr_headers, admin_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    _rule(client, admin_headers)

    first = client.post("/api/v1/alert-rules/evaluate", headers=admin_headers).json()
    second = client.post("/api/v1/alert-rules/evaluate", headers=admin_headers).json()

    assert first["triggers"] > 0
    assert second["triggers"] == 0
    assert second["suppressed"] >= first["triggers"]


def test_between_rule_requires_a_secondary_threshold(client, admin_headers):
    resp = _rule(client, admin_headers, operator="between", secondary_threshold=None)
    assert resp.status_code == 422


def test_department_scoped_rule_needs_a_department(client, admin_headers):
    resp = _rule(client, admin_headers, scope="department", department_id=None)
    assert resp.status_code == 400


def test_rule_triggers_are_recorded(client, hr_headers, admin_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    rule = _rule(client, admin_headers).json()
    client.post("/api/v1/alert-rules/evaluate", headers=admin_headers)

    triggers = client.get(
        f"/api/v1/alert-rules/{rule['id']}/triggers", headers=admin_headers
    ).json()
    assert triggers["meta"]["total"] > 0
    assert triggers["items"][0]["metric_value"] >= 1.0


def test_comparison_operators():
    from app.services.alert_engine import compare

    assert compare(10, RuleOperator.GREATER_THAN, 5)
    assert not compare(5, RuleOperator.GREATER_THAN, 5)
    assert compare(5, RuleOperator.GREATER_OR_EQUAL, 5)
    assert compare(3, RuleOperator.LESS_THAN, 5)
    assert compare(5, RuleOperator.BETWEEN, 1, 10)
    assert not compare(15, RuleOperator.BETWEEN, 1, 10)


# ------------------------------------------------------------------- forecasts
def test_projection_widens_with_distance():
    from app.ml.forecaster import project

    result = project([10, 12, 11, 13, 14, 15], periods=4)
    assert result["method"] == "linear_regression"
    widths = [
        p["upper_bound"] - p["lower_bound"] for p in result["points"]
    ]
    assert widths[-1] > widths[0]


def test_too_little_history_falls_back_to_the_mean():
    from app.ml.forecaster import project

    result = project([10, 12], periods=3)
    assert result["method"] == "mean"
    assert "Too few" in result["note"]


def test_attrition_forecast_is_bounded_to_a_percentage(client, hr_headers, org):
    resp = client.post(
        "/api/v1/forecasting",
        json={"name": "Attrition 6m", "forecast_type": "attrition_rate",
              "horizon_periods": 6, "lookback_periods": 12},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    projections = [p for p in body["data_points"] if p["is_projection"]]
    assert len(projections) == 6
    assert all(0 <= p["predicted_value"] <= 100 for p in projections)


def test_forecast_records_its_caveat(client, hr_headers, org):
    body = client.post(
        "/api/v1/forecasting",
        json={"name": "Headcount", "forecast_type": "headcount"},
        headers=hr_headers,
    ).json()
    assert "caveat" in body["assumptions"]


def test_scenario_states_its_assumption(client, hr_headers, org):
    forecast = client.post(
        "/api/v1/forecasting",
        json={"name": "Attrition", "forecast_type": "attrition_rate"},
        headers=hr_headers,
    ).json()

    resp = client.post(
        f"/api/v1/forecasting/{forecast['id']}/scenarios",
        json={"name": "8% raise", "salary_increase_percent": 8.0},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "assumption" in body["results"]
    assert body["results"]["salary_effect_applied"] < 0


# ---------------------------------------------------------------- interventions
def _plan(client, headers, employee_id, **overrides):
    payload = {
        "employee_id": employee_id,
        "title": "Retention conversation and salary review",
        "intervention_type": "salary_revision",
        "priority": "high",
        "start_date": date.today().isoformat(),
    }
    payload.update(overrides)
    return client.post("/api/v1/interventions", json=payload, headers=headers)


def test_plan_captures_the_before_score(client, hr_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    resp = _plan(client, hr_headers, org["reportee_id"])
    assert resp.status_code == 201
    assert resp.json()["risk_score_before"] is not None


def test_only_one_open_plan_per_employee(client, hr_headers, org):
    _plan(client, hr_headers, org["reportee_id"])
    second = _plan(client, hr_headers, org["reportee_id"], title="Another plan")
    assert second.status_code == 400
    assert "already open" in second.json()["error"]["message"].lower()


def test_completing_requires_all_actions_closed(client, hr_headers, org):
    plan = _plan(client, hr_headers, org["reportee_id"]).json()
    client.post(
        f"/api/v1/interventions/{plan['id']}/actions",
        json={"title": "Schedule the salary review"},
        headers=hr_headers,
    )

    blocked = client.patch(
        f"/api/v1/interventions/{plan['id']}",
        json={"status": "completed"},
        headers=hr_headers,
    )
    assert blocked.status_code == 400
    assert "still open" in blocked.json()["error"]["message"].lower()


def test_completing_after_closing_actions(client, hr_headers, org):
    client.post("/api/v1/risk/evaluate", headers=hr_headers)
    plan = _plan(client, hr_headers, org["reportee_id"]).json()
    action = client.post(
        f"/api/v1/interventions/{plan['id']}/actions",
        json={"title": "Schedule the salary review"},
        headers=hr_headers,
    ).json()

    client.post(
        f"/api/v1/interventions/actions/{action['id']}/complete",
        json={"notes": "Done"},
        headers=hr_headers,
    )
    done = client.patch(
        f"/api/v1/interventions/{plan['id']}",
        json={"status": "completed", "outcome": "successful"},
        headers=hr_headers,
    )
    assert done.status_code == 200
    assert done.json()["risk_score_after"] is not None


def test_adding_an_action_moves_the_plan_in_progress(client, hr_headers, org):
    plan = _plan(client, hr_headers, org["reportee_id"]).json()
    assert plan["status"] == "planned"

    client.post(
        f"/api/v1/interventions/{plan['id']}/actions",
        json={"title": "Book a 1:1"},
        headers=hr_headers,
    )
    refreshed = client.get(
        f"/api/v1/interventions/{plan['id']}", headers=hr_headers
    ).json()
    assert refreshed["status"] == "in_progress"


def test_effectiveness_carries_the_causal_caveat(client, hr_headers, org):
    resp = client.get("/api/v1/interventions/effectiveness", headers=hr_headers)
    assert resp.status_code == 200
    assert "correlation" in resp.json()["caveat"].lower()


# ----------------------------------------------------------------- analytics
def test_overview_separates_voluntary_from_involuntary(client, hr_headers, org):
    resp = client.get("/api/v1/analytics/attrition/overview", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "voluntary_exits" in body
    assert "involuntary_exits" in body
    assert len(body["trend"]) == 12


def test_tenure_bands_cover_everyone(client, hr_headers, org):
    resp = client.get("/api/v1/analytics/attrition/by-tenure", headers=hr_headers)
    assert resp.status_code == 200
    bands = resp.json()
    assert len(bands) == 5
    assert sum(b["employees"] for b in bands) == 4


def test_drivers_reports_no_model_gracefully(client, hr_headers, org):
    resp = client.get("/api/v1/analytics/attrition/drivers", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json()["model"] is None


def test_risk_distribution_counts_unscored(client, hr_headers, org):
    resp = client.get(
        "/api/v1/analytics/attrition/risk-distribution", headers=hr_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["unscored"] + body["total_scored"] == 4


def test_manager_cannot_read_org_analytics(client, manager_headers, org):
    resp = client.get("/api/v1/analytics/attrition/overview", headers=manager_headers)
    assert resp.status_code == 403
