"""Employee CRUD, scoping, history and import tests."""

from datetime import date

from tests.conftest import TEST_PASSWORD


# ------------------------------------------------------------------- create
def test_hr_can_create_an_employee(client, hr_headers, org):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Arun",
            "last_name": "Kumar",
            "work_email": "arun.kumar@test.com",
            "date_of_joining": "2024-01-15",
            "department_id": org["eng_id"],
            "designation_id": org["senior_id"],
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["employee"]["full_name"] == "Arun Kumar"
    assert body["user_created"] is False


def test_employee_code_is_generated_sequentially(client, hr_headers, org):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Auto",
            "work_email": "auto@test.com",
            "date_of_joining": "2024-02-01",
        },
        headers=hr_headers,
    )
    # org fixture already used EMP0001..EMP0004
    assert resp.json()["employee"]["employee_code"] == "EMP0005"


def test_creating_with_a_user_account_returns_temp_password(client, hr_headers):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Login",
            "last_name": "Person",
            "work_email": "login.person@test.com",
            "date_of_joining": "2024-03-01",
            "create_user_account": True,
            "user_role": "employee",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user_created"] is True
    assert body["temporary_password"]

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "login.person@test.com",
            "password": body["temporary_password"],
        },
    )
    assert login.status_code == 200


def test_duplicate_work_email_rejected(client, hr_headers, org):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Clone",
            "work_email": "employee@test.com",
            "date_of_joining": "2024-01-01",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 409


def test_unknown_department_rejected(client, hr_headers):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Ghost",
            "work_email": "ghost@test.com",
            "date_of_joining": "2024-01-01",
            "department_id": 9999,
        },
        headers=hr_headers,
    )
    assert resp.status_code == 404


def test_future_dob_rejected(client, hr_headers):
    resp = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Timely",
            "work_email": "timely@test.com",
            "date_of_joining": "2024-01-01",
            "date_of_birth": "2099-01-01",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------ scoping
def test_hr_sees_every_employee(client, hr_headers, org):
    resp = client.get("/api/v1/employees", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 4


def test_manager_sees_only_self_and_reportees(client, manager_headers, org):
    resp = client.get("/api/v1/employees", headers=manager_headers)
    assert resp.status_code == 200
    codes = {e["employee_code"] for e in resp.json()["items"]}
    assert codes == {"EMP0002", "EMP0003"}


def test_employee_role_cannot_list_employees(client, employee_headers, org):
    """The employee role holds no employee:read; self-service goes through /me."""
    resp = client.get("/api/v1/employees", headers=employee_headers)
    assert resp.status_code == 403


def test_self_scoping_returns_only_own_record(client, employee_headers, org, db_session):
    """
    Grant employee:read to the employee role, then confirm the row-level scope
    still narrows the result to the caller's own record.
    """
    from sqlalchemy import select

    from app.models.role import Permission, Role

    role = db_session.execute(select(Role).where(Role.name == "employee")).scalar_one()
    perm = db_session.execute(
        select(Permission).where(Permission.code == "employee:read")
    ).scalar_one()
    role.permissions.append(perm)
    db_session.commit()

    resp = client.get("/api/v1/employees", headers=employee_headers)
    assert resp.status_code == 200
    assert resp.json()["meta"]["total"] == 1
    assert resp.json()["items"][0]["employee_code"] == "EMP0003"


def test_employee_cannot_read_another_record(client, employee_headers, org):
    resp = client.get(f"/api/v1/employees/{org['outsider_id']}", headers=employee_headers)
    assert resp.status_code == 403


def test_manager_can_read_their_reportee(client, manager_headers, org):
    resp = client.get(f"/api/v1/employees/{org['reportee_id']}", headers=manager_headers)
    assert resp.status_code == 200


def test_manager_cannot_read_an_unrelated_employee(client, manager_headers, org):
    resp = client.get(f"/api/v1/employees/{org['outsider_id']}", headers=manager_headers)
    assert resp.status_code == 403


def test_me_returns_linked_profile(client, employee_headers, org):
    resp = client.get("/api/v1/employees/me", headers=employee_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["employee_code"] == "EMP0003"
    assert body["manager_name"] == "Meera Manager"
    assert body["department_name"] == "Engineering"


def test_me_fails_without_a_linked_profile(client, admin_headers):
    resp = client.get("/api/v1/employees/me", headers=admin_headers)
    assert resp.status_code == 400


# ------------------------------------------------------------------ history
def test_joining_event_recorded_on_create(client, hr_headers, org):
    created = client.post(
        "/api/v1/employees",
        json={
            "first_name": "Historic",
            "work_email": "historic@test.com",
            "date_of_joining": "2024-04-01",
        },
        headers=hr_headers,
    ).json()
    history = client.get(
        f"/api/v1/employees/{created['employee']['id']}/history", headers=hr_headers
    ).json()
    assert len(history) == 1
    assert history[0]["event_type"] == "joined"


def test_salary_change_writes_history_and_hike_percent(client, hr_headers, org):
    resp = client.patch(
        f"/api/v1/employees/{org['reportee_id']}",
        json={"current_salary": 750000},
        headers=hr_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["last_hike_percent"] == 25.0

    history = client.get(
        f"/api/v1/employees/{org['reportee_id']}/history", headers=hr_headers
    ).json()
    events = [h["event_type"] for h in history]
    assert "salary_revision" in events


def test_department_transfer_writes_history(client, hr_headers, org):
    client.patch(
        f"/api/v1/employees/{org['reportee_id']}",
        json={"department_id": org["hr_dept_id"]},
        headers=hr_headers,
    )
    history = client.get(
        f"/api/v1/employees/{org['reportee_id']}/history", headers=hr_headers
    ).json()
    assert "transfer" in [h["event_type"] for h in history]


def test_unchanged_value_writes_no_history(client, hr_headers, org):
    before = len(
        client.get(
            f"/api/v1/employees/{org['reportee_id']}/history", headers=hr_headers
        ).json()
    )
    client.patch(
        f"/api/v1/employees/{org['reportee_id']}",
        json={"department_id": org["eng_id"]},  # already Engineering
        headers=hr_headers,
    )
    after = len(
        client.get(
            f"/api/v1/employees/{org['reportee_id']}/history", headers=hr_headers
        ).json()
    )
    assert after == before


# ------------------------------------------------------------- org hierarchy
def test_employee_cannot_be_their_own_manager(client, hr_headers, org):
    resp = client.patch(
        f"/api/v1/employees/{org['reportee_id']}",
        json={"manager_id": org["reportee_id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_manager_cycle_is_rejected(client, hr_headers, org):
    # Meera already manages Eshan; making Eshan manage Meera closes the loop
    resp = client.patch(
        f"/api/v1/employees/{org['manager_id']}",
        json={"manager_id": org["reportee_id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 400
    assert "cycle" in resp.json()["error"]["message"].lower()


def test_team_endpoint_lists_reportees(client, manager_headers, org):
    resp = client.get(f"/api/v1/employees/{org['manager_id']}/team", headers=manager_headers)
    assert resp.status_code == 200
    assert [m["employee_code"] for m in resp.json()] == ["EMP0003"]


def test_org_chart_nests_reportees(client, hr_headers, org):
    tree = client.get("/api/v1/employees/org-chart", headers=hr_headers).json()
    meera = next(n for n in tree if n["employee_code"] == "EMP0002")
    assert [r["employee_code"] for r in meera["reportees"]] == ["EMP0003"]


# --------------------------------------------------------------------- exit
def test_exit_blocked_while_reportees_remain(client, hr_headers, org):
    resp = client.post(
        f"/api/v1/employees/{org['manager_id']}/exit",
        json={
            "date_of_exit": "2026-01-31",
            "status": "resigned",
            "exit_reason": "Better opportunity",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 400
    assert "report" in resp.json()["error"]["message"].lower()


def test_exit_deactivates_the_linked_user(client, hr_headers, org):
    resp = client.post(
        f"/api/v1/employees/{org['reportee_id']}/exit",
        json={
            "date_of_exit": "2026-01-31",
            "status": "resigned",
            "exit_reason": "Relocating",
            "deactivate_user": True,
        },
        headers=hr_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resigned"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@test.com", "password": TEST_PASSWORD},
    )
    assert login.status_code == 401


def test_exit_date_before_joining_rejected(client, hr_headers, org):
    resp = client.post(
        f"/api/v1/employees/{org['outsider_id']}/exit",
        json={
            "date_of_exit": "2020-01-01",
            "status": "resigned",
            "exit_reason": "Time travel",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_invalid_exit_status_rejected(client, hr_headers, org):
    resp = client.post(
        f"/api/v1/employees/{org['outsider_id']}/exit",
        json={
            "date_of_exit": "2026-01-01",
            "status": "active",
            "exit_reason": "Not really leaving",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------- import
def test_csv_import_creates_and_reports_failures(client, hr_headers, org):
    csv_content = (
        "first_name,last_name,work_email,date_of_joining,department_code,manager_code\n"
        "Vikram,Rao,vikram@test.com,2024-05-01,ENG,EMP0002\n"
        "Divya,Nair,divya@test.com,2024-05-02,ENG,\n"
        "Broken,Row,bad-date@test.com,not-a-date,ENG,\n"
        "NoManager,Row,nomgr@test.com,2024-05-03,ENG,EMP9999\n"
    )
    resp = client.post(
        "/api/v1/employees/import",
        files={"file": ("staff.csv", csv_content, "text/csv")},
        headers=hr_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert len(body["failures"]) == 2
    assert {f["row_number"] for f in body["failures"]} == {4, 5}


def test_csv_import_skips_existing_emails(client, hr_headers, org):
    csv_content = (
        "first_name,work_email,date_of_joining\n"
        "Duplicate,employee@test.com,2024-05-01\n"
    )
    resp = client.post(
        "/api/v1/employees/import",
        files={"file": ("staff.csv", csv_content, "text/csv")},
        headers=hr_headers,
    )
    assert resp.json()["skipped"] == 1
    assert resp.json()["created"] == 0


def test_non_csv_upload_rejected(client, hr_headers):
    resp = client.post(
        "/api/v1/employees/import",
        files={"file": ("staff.xlsx", b"not a csv", "application/vnd.ms-excel")},
        headers=hr_headers,
    )
    assert resp.status_code == 422


def test_employee_cannot_import(client, employee_headers):
    resp = client.post(
        "/api/v1/employees/import",
        files={"file": ("staff.csv", "first_name\nX\n", "text/csv")},
        headers=employee_headers,
    )
    assert resp.status_code == 403
