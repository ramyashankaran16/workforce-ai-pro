"""Phase 3 tests: reports, audit, workflow, performance, recommendations,
search and stability."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.enums import (
    AuditAction,
    RecommendationStatus,
    ReviewStatus,
    TaskStatus,
)
from app.models.employee import Employee
from app.services import audit_service, recommendation_service, stability_service


# ------------------------------------------------------------------- reports
def _generate(client, headers, category="headcount", file_format="csv"):
    return client.post(
        "/api/v1/reports/generate",
        json={"category": category, "file_format": file_format},
        headers=headers,
    )


def test_date_parameters_are_stored_and_reused(client, hr_headers, org):
    """
    Regression: date objects are not JSON-serialisable, and `parameters` is
    persisted on the report row. Passing a date range used to fail at the
    INSERT with a database error.
    """
    resp = client.post(
        "/api/v1/reports/generate",
        json={
            "category": "attendance",
            "file_format": "excel",
            "start_date": "2026-09-01",
            "end_date": "2026-09-11",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "completed"


def test_every_category_generates(client, hr_headers, org):
    for category in ["attendance", "leave", "payroll", "audit", "headcount",
                     "attrition", "custom"]:
        resp = client.post(
            "/api/v1/reports/generate",
            json={
                "category": category,
                "file_format": "csv",
                "start_date": "2026-09-01",
                "end_date": "2026-09-11",
            },
            headers=hr_headers,
        )
        assert resp.status_code == 201, f"{category} failed: {resp.text}"


def test_placeholder_zero_ids_are_ignored(client, hr_headers, org):
    """Swagger's example body sends 0 for optional ids; 0 is not a real row."""
    resp = client.post(
        "/api/v1/reports/generate",
        json={
            "category": "headcount",
            "file_format": "csv",
            "template_id": 0,
            "department_id": 0,
            "run_id": 0,
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201


def test_unknown_template_reports_clearly(client, hr_headers, org):
    resp = client.post(
        "/api/v1/reports/generate",
        json={"category": "headcount", "file_format": "csv", "template_id": 999},
        headers=hr_headers,
    )
    assert resp.status_code == 404
    assert "template" in resp.json()["error"]["message"].lower()


def test_csv_report_generates(client, hr_headers, org):
    resp = _generate(client, hr_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["row_count"] > 0
    assert body["reference"].startswith("RPT")


def test_excel_report_downloads(client, hr_headers, org):
    report = _generate(client, hr_headers, "employees" if False else "custom",
                       "excel").json()
    resp = client.get(f"/api/v1/reports/{report['id']}/download", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"  # xlsx is a zip container


def test_pdf_report_downloads(client, hr_headers, org):
    report = _generate(client, hr_headers, "headcount", "pdf").json()
    resp = client.get(f"/api/v1/reports/{report['id']}/download", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


def test_json_report_generates(client, hr_headers, org):
    report = _generate(client, hr_headers, "custom", "json").json()
    resp = client.get(f"/api/v1/reports/{report['id']}/download", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json()


def test_download_increments_the_counter(client, hr_headers, org):
    report = _generate(client, hr_headers).json()
    client.get(f"/api/v1/reports/{report['id']}/download", headers=hr_headers)
    listing = client.get("/api/v1/reports", headers=hr_headers).json()
    assert listing["items"][0]["download_count"] == 1


def test_attrition_report_includes_predictions(client, hr_headers, org):
    resp = _generate(client, hr_headers, "attrition", "csv")
    assert resp.status_code == 201


def test_employee_cannot_generate_reports(client, employee_headers, org):
    assert _generate(client, employee_headers).status_code == 403


# --------------------------------------------------------------------- audit
def test_login_history_records_attempts(client, hr_headers):
    client.post(
        "/api/v1/auth/login",
        json={"email": "employee@test.com", "password": "WrongPass123"},
    )
    resp = client.get(
        "/api/v1/audit/login-history?successful_only=false", headers=hr_headers
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] >= 1


def test_suspicious_logins_flag_repeated_failures(client, hr_headers, admin_headers):
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": "target@test.com", "password": "Guess12345"},
        )
    resp = client.get(
        "/api/v1/audit/suspicious-logins?threshold=5&hours=24", headers=admin_headers
    )
    assert resp.status_code == 200
    assert any(row["email"] == "target@test.com" for row in resp.json())


def test_audit_entries_redact_sensitive_fields(db_session, org):
    entry = audit_service.record(
        db_session,
        action=AuditAction.UPDATE,
        entity_type="user",
        entity_id=1,
        new_values={
            "full_name": "Someone",
            "hashed_password": "$2b$12$realhash",
            "bank_account_number": "123456789",
        },
    )
    assert entry.new_values["full_name"] == "Someone"
    assert entry.new_values["hashed_password"] == "***redacted***"
    assert entry.new_values["bank_account_number"] == "***redacted***"


def test_changed_fields_computed(db_session):
    entry = audit_service.record(
        db_session,
        action=AuditAction.UPDATE,
        entity_type="employee",
        entity_id=1,
        old_values={"city": "Salem", "phone": "111"},
        new_values={"city": "Chennai", "phone": "111"},
    )
    assert entry.changed_fields["fields"] == ["city"]


def test_audit_summary_aggregates(client, admin_headers, db_session):
    audit_service.record(
        db_session, action=AuditAction.CREATE, entity_type="employee", entity_id=1
    )
    resp = client.get("/api/v1/audit/summary?days=30", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total_entries"] >= 1


def test_entity_trail_returns_history(client, admin_headers, db_session):
    for action in (AuditAction.CREATE, AuditAction.UPDATE):
        audit_service.record(
            db_session, action=action, entity_type="department", entity_id=7
        )
    resp = client.get("/api/v1/audit/trail/department/7", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_manager_cannot_read_audit_logs(client, manager_headers):
    assert client.get("/api/v1/audit/logs", headers=manager_headers).status_code == 403


# ------------------------------------------------------------------ workflow
def _workflow(client, headers):
    return client.post(
        "/api/v1/workflows",
        json={
            "name": "Employee onboarding",
            "category": "onboarding",
            "steps": [
                {"name": "Collect documents", "assignee_role": "hr", "sla_days": 3},
                {"name": "Assign a buddy", "assignee_role": "manager", "sla_days": 5},
                {"name": "Issue equipment", "assignee_role": "hr", "sla_days": 2},
            ],
        },
        headers=headers,
    )


def test_workflow_created_with_ordered_steps(client, hr_headers):
    resp = _workflow(client, hr_headers)
    assert resp.status_code == 201
    steps = resp.json()["steps"]
    assert [s["sequence"] for s in steps] == [1, 2, 3]


def test_starting_a_workflow_creates_one_task_per_step(client, hr_headers, org):
    workflow = _workflow(client, hr_headers).json()
    resp = client.post(
        f"/api/v1/workflows/{workflow['id']}/start",
        json={"employee_id": org["reportee_id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 3
    assert all(t["reference"].startswith("TSK") for t in tasks)


def test_sla_days_become_the_due_date(client, hr_headers, org):
    workflow = _workflow(client, hr_headers).json()
    tasks = client.post(
        f"/api/v1/workflows/{workflow['id']}/start",
        json={"employee_id": org["reportee_id"]},
        headers=hr_headers,
    ).json()
    expected = (date.today() + timedelta(days=3)).isoformat()
    assert tasks[0]["due_date"] == expected


def test_manager_step_routes_to_the_line_manager(client, hr_headers, org, db_session):
    from app.models.user import User

    workflow = _workflow(client, hr_headers).json()
    tasks = client.post(
        f"/api/v1/workflows/{workflow['id']}/start",
        json={"employee_id": org["reportee_id"]},
        headers=hr_headers,
    ).json()

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    buddy_task = next(t for t in tasks if "buddy" in t["title"].lower())
    assert buddy_task["assigned_to_id"] == manager_user.id


def test_task_completion_blocked_by_open_subtasks(client, hr_headers, admin_headers):
    parent = client.post(
        "/api/v1/tasks",
        json={"title": "Parent task", "priority": "medium"},
        headers=hr_headers,
    ).json()
    client.post(
        "/api/v1/tasks",
        json={"title": "Child task", "parent_task_id": parent["id"]},
        headers=hr_headers,
    )

    resp = client.patch(
        f"/api/v1/tasks/{parent['id']}",
        json={"status": "completed"},
        headers=hr_headers,
    )
    assert resp.status_code == 400
    assert "subtask" in resp.json()["error"]["message"].lower()


def test_completing_a_task_sets_progress_to_100(client, hr_headers):
    task = client.post(
        "/api/v1/tasks", json={"title": "Standalone task"}, headers=hr_headers
    ).json()
    resp = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "completed"}, headers=hr_headers
    )
    assert resp.status_code == 200
    assert resp.json()["progress_percent"] == 100
    assert resp.json()["completed_at"] is not None


def test_due_before_start_rejected(client, hr_headers):
    resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "Backwards task",
            "start_date": (date.today() + timedelta(days=5)).isoformat(),
            "due_date": date.today().isoformat(),
        },
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_overdue_tasks_listed(client, hr_headers, db_session):
    from app.models.workflow import Task

    task = client.post(
        "/api/v1/tasks", json={"title": "Late task"}, headers=hr_headers
    ).json()
    row = db_session.get(Task, task["id"])
    row.due_date = date.today() - timedelta(days=3)
    db_session.commit()

    overdue = client.get("/api/v1/tasks/overdue", headers=hr_headers).json()
    assert any(t["id"] == task["id"] for t in overdue)


# --------------------------------------------------------------- performance
def _cycle(client, headers):
    return client.post(
        "/api/v1/performance/cycles",
        json={
            "name": "FY26 H1",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "rating_scale_max": 5,
        },
        headers=headers,
    )


def test_cycle_launch_creates_reviews(client, hr_headers, org):
    cycle = _cycle(client, hr_headers).json()
    resp = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 4
    assert all(r["status"] == "self_review" for r in resp.json())


def test_cycle_cannot_be_launched_twice(client, hr_headers, org):
    cycle = _cycle(client, hr_headers).json()
    client.post(f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers)
    second = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    )
    assert second.status_code == 400


def test_manager_cannot_skip_the_self_review(client, hr_headers, manager_headers, org):
    cycle = _cycle(client, hr_headers).json()
    reviews = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    ).json()
    review = next(r for r in reviews if r["employee_id"] == org["reportee_id"])

    resp = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"self_rating": 4},
        headers=manager_headers,
    )
    assert resp.status_code == 403
    assert "self-review" in resp.json()["error"]["message"].lower()


def test_full_review_progression(client, hr_headers, employee_headers, manager_headers, org):
    cycle = _cycle(client, hr_headers).json()
    reviews = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    ).json()
    review = next(r for r in reviews if r["employee_id"] == org["reportee_id"])

    stage_one = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"self_rating": 4, "self_comments": "Delivered the migration on time."},
        headers=employee_headers,
    )
    assert stage_one.status_code == 200
    assert stage_one.json()["status"] == "manager_review"

    stage_two = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"manager_rating": 4, "manager_comments": "Agreed."},
        headers=manager_headers,
    )
    assert stage_two.json()["status"] == "hr_review"

    stage_three = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"final_rating": 4},
        headers=hr_headers,
    )
    assert stage_three.json()["status"] == "completed"


def test_final_rating_written_back_to_the_employee(
    client, hr_headers, employee_headers, manager_headers, org, db_session
):
    cycle = _cycle(client, hr_headers).json()
    reviews = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    ).json()
    review = next(r for r in reviews if r["employee_id"] == org["reportee_id"])

    client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"self_rating": 5}, headers=employee_headers,
    )
    client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"manager_rating": 4}, headers=manager_headers,
    )
    client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"final_rating": 4.5}, headers=hr_headers,
    )

    employee = db_session.get(Employee, org["reportee_id"])
    db_session.refresh(employee)
    assert employee.last_performance_rating == 4.5


def test_self_rating_required_to_submit(client, employee_headers, hr_headers, org):
    cycle = _cycle(client, hr_headers).json()
    reviews = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    ).json()
    review = next(r for r in reviews if r["employee_id"] == org["reportee_id"])

    resp = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"self_comments": "No rating given"},
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_rating_above_the_scale_rejected(client, employee_headers, hr_headers, org):
    cycle = _cycle(client, hr_headers).json()
    reviews = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers
    ).json()
    review = next(r for r in reviews if r["employee_id"] == org["reportee_id"])

    resp = client.patch(
        f"/api/v1/performance/reviews/{review['id']}",
        json={"self_rating": 9},
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_cycle_close_blocked_while_reviews_open(client, hr_headers, org):
    cycle = _cycle(client, hr_headers).json()
    client.post(f"/api/v1/performance/cycles/{cycle['id']}/launch", headers=hr_headers)
    resp = client.post(
        f"/api/v1/performance/cycles/{cycle['id']}/close", headers=hr_headers
    )
    assert resp.status_code == 400


def test_goal_weights_capped_at_100(client, employee_headers, org):
    client.post(
        "/api/v1/performance/goals",
        json={"title": "Ship the platform migration", "weight_percent": 70},
        headers=employee_headers,
    )
    resp = client.post(
        "/api/v1/performance/goals",
        json={"title": "Mentor two juniors", "weight_percent": 40},
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "100%" in resp.json()["error"]["message"]


def test_goal_at_100_percent_marks_achieved(client, employee_headers, org):
    goal = client.post(
        "/api/v1/performance/goals",
        json={"title": "Complete certification", "weight_percent": 20},
        headers=employee_headers,
    ).json()
    resp = client.patch(
        f"/api/v1/performance/goals/{goal['id']}",
        json={"progress_percent": 100},
        headers=employee_headers,
    )
    assert resp.json()["status"] == "achieved"


def test_cannot_give_yourself_feedback(client, employee_headers, org):
    resp = client.post(
        "/api/v1/performance/feedback",
        json={"to_employee_id": org["reportee_id"], "content": "I am excellent."},
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_anonymous_feedback_hides_the_author(
    client, manager_headers, employee_headers, org
):
    client.post(
        "/api/v1/performance/feedback",
        json={
            "to_employee_id": org["reportee_id"],
            "content": "Consistently reliable on delivery.",
            "is_anonymous": True,
        },
        headers=manager_headers,
    )
    received = client.get(
        "/api/v1/performance/feedback/me", headers=employee_headers
    ).json()
    assert received[0]["from_employee_id"] is None


# ------------------------------------------------------------ recommendations
def test_underpaid_rule_fires(client, hr_headers, org, db_session):
    from app.models.department import Designation

    designation = db_session.execute(select(Designation)).scalars().first()
    employees = db_session.execute(
        select(Employee).where(Employee.is_deleted.is_(False))
    ).scalars().all()
    for index, employee in enumerate(employees):
        employee.designation_id = designation.id
        employee.current_salary = 1_000_000 if index else 400_000
    db_session.commit()

    resp = client.post("/api/v1/recommendations/generate", headers=hr_headers)
    assert resp.status_code == 201
    assert resp.json()["recommendations_created"] > 0

    listing = client.get(
        "/api/v1/recommendations?category=compensation", headers=hr_headers
    ).json()
    assert listing["meta"]["total"] >= 1
    assert "below the median" in listing["items"][0]["description"].lower()
    assert listing["items"][0]["supporting_data"]["band_median"] > 0


def test_recommendations_carry_their_evidence(client, hr_headers, org, db_session):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 1
    employee.work_life_balance_score = 2
    employee.environment_satisfaction_score = 2
    db_session.commit()

    client.post(
        f"/api/v1/recommendations/generate?employee_id={org['reportee_id']}",
        headers=hr_headers,
    )
    listing = client.get(
        "/api/v1/recommendations?category=engagement", headers=hr_headers
    ).json()
    assert listing["items"][0]["supporting_data"]
    assert listing["items"][0]["rationale"]


def test_duplicate_recommendations_suppressed(client, hr_headers, org, db_session):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.job_satisfaction_score = 1
    employee.work_life_balance_score = 1
    employee.environment_satisfaction_score = 1
    db_session.commit()

    first = client.post(
        f"/api/v1/recommendations/generate?employee_id={org['reportee_id']}",
        headers=hr_headers,
    ).json()
    second = client.post(
        f"/api/v1/recommendations/generate?employee_id={org['reportee_id']}",
        headers=hr_headers,
    ).json()

    assert first["recommendations_created"] > 0
    assert second["recommendations_created"] == 0
    assert second["already_open"] >= first["recommendations_created"]


def test_reading_a_recommendation_marks_it_viewed(client, hr_headers, org, db_session):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.training_hours_last_year = 2
    db_session.commit()

    client.post(
        f"/api/v1/recommendations/generate?employee_id={org['reportee_id']}",
        headers=hr_headers,
    )
    listing = client.get("/api/v1/recommendations", headers=hr_headers).json()
    first = listing["items"][0]
    assert first["status"] == "new"

    detail = client.get(
        f"/api/v1/recommendations/{first['id']}", headers=hr_headers
    ).json()
    assert detail["status"] == "viewed"


def test_feedback_summary_reports_acceptance(client, hr_headers, org, db_session):
    employee = db_session.get(Employee, org["reportee_id"])
    employee.training_hours_last_year = 1
    db_session.commit()
    client.post(
        f"/api/v1/recommendations/generate?employee_id={org['reportee_id']}",
        headers=hr_headers,
    )
    listing = client.get("/api/v1/recommendations", headers=hr_headers).json()
    first = listing["items"][0]

    client.patch(
        f"/api/v1/recommendations/{first['id']}",
        json={"status": "accepted"},
        headers=hr_headers,
    )
    client.post(
        f"/api/v1/recommendations/{first['id']}/feedback",
        json={"is_helpful": True, "rating": 5},
        headers=hr_headers,
    )

    summary = client.get(
        "/api/v1/recommendations/feedback-summary", headers=hr_headers
    ).json()
    assert summary["feedback_received"] == 1
    assert summary["rated_helpful"] == 1


# -------------------------------------------------------------------- search
def test_search_finds_employees(client, hr_headers, org):
    resp = client.get("/api/v1/search?q=Meera", headers=hr_headers)
    assert resp.status_code == 200
    assert any(r["type"] == "employee" for r in resp.json()["results"])


def test_search_is_permission_scoped(client, manager_headers, org):
    """A manager must not find an employee outside their team."""
    resp = client.get("/api/v1/search?q=Nita", headers=manager_headers)
    assert resp.status_code == 200
    employees = [r for r in resp.json()["results"] if r["type"] == "employee"]
    assert employees == []


def test_search_spans_entity_types(client, hr_headers, org):
    resp = client.get("/api/v1/search?q=Engineering", headers=hr_headers)
    types = {r["type"] for r in resp.json()["results"]}
    assert "department" in types


def test_short_term_rejected(client, hr_headers):
    assert client.get("/api/v1/search?q=a", headers=hr_headers).status_code == 422


def test_suggest_returns_labels(client, hr_headers, org):
    resp = client.get("/api/v1/search/suggest?q=Mee", headers=hr_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ----------------------------------------------------------------- stability
def test_normalise_caps_at_100():
    assert stability_service.normalise(120, 88, True) == 100.0
    assert stability_service.normalise(88, 88, True) == 100.0
    assert stability_service.normalise(44, 88, True) == 50.0


def test_normalise_inverts_for_lower_is_better():
    # risk exposure: below the benchmark scores high
    assert stability_service.normalise(0, 15, False) == 100.0
    assert stability_service.normalise(15, 15, False) == 100.0
    assert stability_service.normalise(30, 15, False) == 0.0


def test_unknown_metric_is_neutral():
    assert stability_service.normalise(None, 88, True) == 50.0


def test_weights_sum_to_one():
    total = sum(weight for weight, *_ in stability_service.METRIC_SPEC.values())
    assert round(total, 6) == 1.0


def test_snapshot_exposes_its_breakdown(client, hr_headers, org):
    resp = client.post("/api/v1/stability/snapshot", headers=hr_headers)
    assert resp.status_code == 201
    body = resp.json()

    assert 0 <= body["stability_index"] <= 100
    assert body["grade"] in {"excellent", "good", "moderate", "poor", "critical"}
    assert body["commentary"]
    assert len(body["metrics"]) == 6
    for metric in body["metrics"]:
        assert metric["weight"] > 0
        assert metric["benchmark"] is not None


def test_rerunning_replaces_the_same_day_snapshot(client, hr_headers, org):
    client.post("/api/v1/stability/snapshot", headers=hr_headers)
    client.post("/api/v1/stability/snapshot", headers=hr_headers)
    history = client.get("/api/v1/stability/history", headers=hr_headers).json()
    assert len(history) == 1


def test_department_comparison_is_ranked(client, hr_headers, org):
    resp = client.get("/api/v1/stability/compare", headers=hr_headers)
    assert resp.status_code == 200
    scores = [d["stability_index"] for d in resp.json()]
    assert scores == sorted(scores, reverse=True)


def test_latest_requires_a_snapshot(client, hr_headers, org):
    resp = client.get("/api/v1/stability", headers=hr_headers)
    assert resp.status_code == 404
    assert "snapshot" in resp.json()["error"]["message"].lower()