"""Payroll computation, workflow and immutability tests."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.attendance import Attendance
from app.models.enums import AttendanceStatus, PayComponentType
from app.models.payroll import SalaryStructure
from app.services import payroll_service


@pytest.fixture
def structure(db_session, org):
    """A 50,000/month structure for the reportee: 40k gross, 3.7k deductions."""
    return payroll_service.create_structure(
        db_session,
        {
            "employee_id": org["reportee_id"],
            "ctc": Decimal("600000.00"),
            "basic_salary": Decimal("25000.00"),
            "hra": Decimal("10000.00"),
            "conveyance_allowance": Decimal("2000.00"),
            "medical_allowance": Decimal("1500.00"),
            "special_allowance": Decimal("1500.00"),
            "provident_fund": Decimal("3000.00"),
            "professional_tax": Decimal("200.00"),
            "income_tax": Decimal("500.00"),
            "other_deductions": Decimal("0.00"),
            "effective_from": date(2026, 1, 1),
        },
    )


# ------------------------------------------------------------------- rounding
def test_money_rounds_half_up():
    assert payroll_service.money(Decimal("100.005")) == Decimal("100.01")
    assert payroll_service.money(Decimal("100.004")) == Decimal("100.00")
    assert payroll_service.money(0.1) + payroll_service.money(0.2) == Decimal("0.30")


def test_structure_totals(db_session, structure):
    totals = payroll_service.structure_totals(structure)
    assert totals["gross_earnings"] == Decimal("40000.00")
    assert totals["total_deductions"] == Decimal("3700.00")
    assert totals["net_monthly"] == Decimal("36300.00")


# ---------------------------------------------------------------- computation
def test_full_month_has_no_loss_of_pay(db_session, structure):
    lines, gross, deductions, net = payroll_service.compute_payslip_lines(
        structure, working_days=22, unpaid_days=0, overtime_hours=0
    )
    assert gross == Decimal("40000.00")
    assert deductions == Decimal("3700.00")
    assert net == Decimal("36300.00")
    assert not any("Loss of Pay" in line["component_name"] for line in lines)


def test_loss_of_pay_charged_per_working_day(db_session, structure):
    # 40000 gross over 20 working days = 2000 per day, two days lost
    lines, gross, deductions, net = payroll_service.compute_payslip_lines(
        structure, working_days=20, unpaid_days=2, overtime_hours=0
    )
    lop = next(l for l in lines if "Loss of Pay" in l["component_name"])
    assert lop["amount"] == Decimal("4000.00")
    assert deductions == Decimal("7700.00")
    assert net == Decimal("32300.00")


def test_half_day_loss_is_charged(db_session, structure):
    lines, _, _, net = payroll_service.compute_payslip_lines(
        structure, working_days=20, unpaid_days=0.5, overtime_hours=0
    )
    lop = next(l for l in lines if "Loss of Pay" in l["component_name"])
    assert lop["amount"] == Decimal("1000.00")


def test_loss_of_pay_never_exceeds_gross(db_session, structure):
    # absurd number of lost days should not produce negative pay beyond zero
    _, gross, deductions, net = payroll_service.compute_payslip_lines(
        structure, working_days=20, unpaid_days=90, overtime_hours=0
    )
    assert deductions <= gross + Decimal("3700.00")
    assert net >= Decimal("-3700.00")


def test_overtime_paid_at_one_and_a_half_times(db_session, structure):
    # basic 25000 / 20 days / 8 hours = 156.25 per hour, x1.5 x4 = 937.50
    lines, gross, _, _ = payroll_service.compute_payslip_lines(
        structure, working_days=20, unpaid_days=0, overtime_hours=4
    )
    overtime = next(l for l in lines if "Overtime" in l["component_name"])
    assert overtime["amount"] == Decimal("937.50")
    assert gross == Decimal("40937.50")


def test_zero_components_produce_no_line(db_session, structure):
    lines, _, _, _ = payroll_service.compute_payslip_lines(
        structure, working_days=22, unpaid_days=0, overtime_hours=0
    )
    names = [l["component_name"] for l in lines]
    assert "Other Deductions" not in names  # it is zero in the fixture


# ------------------------------------------------------- effective-dated rules
def test_new_structure_closes_the_previous_one(db_session, org, structure):
    second = payroll_service.create_structure(
        db_session,
        {
            "employee_id": org["reportee_id"],
            "ctc": Decimal("720000.00"),
            "basic_salary": Decimal("30000.00"),
            "hra": Decimal("12000.00"),
            "conveyance_allowance": Decimal("2000.00"),
            "medical_allowance": Decimal("1500.00"),
            "special_allowance": Decimal("2500.00"),
            "provident_fund": Decimal("3600.00"),
            "professional_tax": Decimal("200.00"),
            "income_tax": Decimal("800.00"),
            "other_deductions": Decimal("0.00"),
            "effective_from": date(2026, 7, 1),
        },
    )
    db_session.refresh(structure)
    assert structure.effective_to == date(2026, 6, 30)
    assert structure.is_active is False
    assert second.is_active is True


def test_active_structure_resolves_by_date(db_session, org, structure):
    payroll_service.create_structure(
        db_session,
        {
            "employee_id": org["reportee_id"],
            "ctc": Decimal("720000.00"),
            "basic_salary": Decimal("30000.00"),
            "hra": Decimal("12000.00"),
            "conveyance_allowance": Decimal("0.00"),
            "medical_allowance": Decimal("0.00"),
            "special_allowance": Decimal("0.00"),
            "provident_fund": Decimal("3600.00"),
            "professional_tax": Decimal("200.00"),
            "income_tax": Decimal("0.00"),
            "other_deductions": Decimal("0.00"),
            "effective_from": date(2026, 7, 1),
        },
    )
    march = payroll_service.active_structure(db_session, org["reportee_id"], date(2026, 3, 31))
    august = payroll_service.active_structure(db_session, org["reportee_id"], date(2026, 8, 31))
    assert march.basic_salary == Decimal("25000.00")
    assert august.basic_salary == Decimal("30000.00")


def test_backdated_structure_rejected(client, hr_headers, org, structure):
    resp = client.post(
        "/api/v1/payroll/structures",
        json={
            "employee_id": org["reportee_id"],
            "ctc": "700000.00",
            "basic_salary": "30000.00",
            "effective_from": "2025-06-01",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_deductions_exceeding_gross_rejected(client, hr_headers, org):
    resp = client.post(
        "/api/v1/payroll/structures",
        json={
            "employee_id": org["reportee_id"],
            "ctc": "600000.00",
            "basic_salary": "10000.00",
            "provident_fund": "20000.00",
            "effective_from": "2026-01-01",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 422


# -------------------------------------------------------------------- the run
def test_duplicate_run_for_a_period_rejected(client, hr_headers):
    first = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=hr_headers
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=hr_headers
    )
    assert second.status_code == 409


def test_run_period_bounds():
    start, end = payroll_service.period_bounds(2, 2026)
    assert start == date(2026, 2, 1)
    assert end == date(2026, 2, 28)

    start, end = payroll_service.period_bounds(2, 2028)  # leap year
    assert end == date(2028, 2, 29)


def test_processing_creates_payslips_and_skips_the_unstructured(
    client, hr_headers, org, structure
):
    run = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=hr_headers
    ).json()

    resp = client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()

    # only the reportee has a structure; the other three are skipped
    assert body["payslips_created"] == 1
    assert body["employees_skipped"] == 3
    assert any("no salary structure" in reason for reason in body["skipped_reasons"])
    assert body["run"]["status"] == "processed"


def test_absent_days_become_loss_of_pay(client, hr_headers, db_session, org, structure):
    # March 2026 has 22 working days; mark two as absent
    for day in [date(2026, 3, 10), date(2026, 3, 11)]:
        db_session.add(
            Attendance(
                employee_id=org["reportee_id"],
                attendance_date=day,
                status=AttendanceStatus.ABSENT,
            )
        )
    db_session.commit()

    run = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=hr_headers
    ).json()
    client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=hr_headers)

    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    slip = payslips["items"][0]
    assert slip["unpaid_leave_days"] == 2.0

    detail = client.get(
        f"/api/v1/payroll/payslips/{slip['id']}", headers=hr_headers
    ).json()
    assert any("Loss of Pay" in i["component_name"] for i in detail["line_items"])


def test_reprocessing_a_draft_replaces_payslips(client, hr_headers, org, structure):
    run = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=hr_headers
    ).json()

    client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=hr_headers)
    second = client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=hr_headers)
    assert second.status_code == 200

    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    assert payslips["meta"]["total"] == 1  # not duplicated


# ---------------------------------------------------------------- immutability
def _processed_run(client, headers):
    run = client.post(
        "/api/v1/payroll/runs", json={"month": 3, "year": 2026}, headers=headers
    ).json()
    client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=headers)
    return run


def test_workflow_draft_to_paid(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)

    approved = client.post(
        f"/api/v1/payroll/runs/{run['id']}/approve", headers=hr_headers
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    paid = client.post(
        f"/api/v1/payroll/runs/{run['id']}/mark-paid", headers=hr_headers
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None


def test_paid_run_cannot_be_reprocessed(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    client.post(f"/api/v1/payroll/runs/{run['id']}/approve", headers=hr_headers)
    client.post(f"/api/v1/payroll/runs/{run['id']}/mark-paid", headers=hr_headers)

    resp = client.post(f"/api/v1/payroll/runs/{run['id']}/process", headers=hr_headers)
    assert resp.status_code == 400
    assert "cannot be reprocessed" in resp.json()["error"]["message"].lower()


def test_adjustment_blocked_on_a_paid_run(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    payslip_id = payslips["items"][0]["id"]

    client.post(f"/api/v1/payroll/runs/{run['id']}/approve", headers=hr_headers)
    client.post(f"/api/v1/payroll/runs/{run['id']}/mark-paid", headers=hr_headers)

    resp = client.post(
        f"/api/v1/payroll/payslips/{payslip_id}/adjustments",
        json={"component_name": "Arrears", "component_type": "earning", "amount": "500.00"},
        headers=hr_headers,
    )
    assert resp.status_code == 400
    assert "next run" in resp.json()["error"]["message"].lower()


def test_adjustment_allowed_on_a_draft_run(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    slip = payslips["items"][0]
    before = Decimal(slip["net_pay"])

    resp = client.post(
        f"/api/v1/payroll/payslips/{slip['id']}/adjustments",
        json={
            "component_name": "February arrears",
            "component_type": "earning",
            "amount": "1500.00",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 200
    assert Decimal(resp.json()["net_pay"]) == before + Decimal("1500.00")


def test_approve_requires_processed_state(client, hr_headers):
    run = client.post(
        "/api/v1/payroll/runs", json={"month": 4, "year": 2026}, headers=hr_headers
    ).json()
    resp = client.post(f"/api/v1/payroll/runs/{run['id']}/approve", headers=hr_headers)
    assert resp.status_code == 400


def test_mark_paid_requires_approval(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    resp = client.post(f"/api/v1/payroll/runs/{run['id']}/mark-paid", headers=hr_headers)
    assert resp.status_code == 400


# ------------------------------------------------------------------- access
def test_employee_can_read_own_payslip(client, hr_headers, employee_headers, org, structure):
    run = _processed_run(client, hr_headers)
    mine = client.get("/api/v1/payroll/payslips/me", headers=employee_headers)
    assert mine.status_code == 200
    assert mine.json()["meta"]["total"] == 1


def test_employee_cannot_read_another_payslip(
    client, hr_headers, manager_headers, org, structure
):
    run = _processed_run(client, hr_headers)
    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    payslip_id = payslips["items"][0]["id"]  # belongs to the reportee

    resp = client.get(
        f"/api/v1/payroll/payslips/{payslip_id}", headers=manager_headers
    )
    assert resp.status_code == 403


def test_employee_cannot_process_payroll(client, employee_headers):
    resp = client.post(
        "/api/v1/payroll/runs", json={"month": 5, "year": 2026}, headers=employee_headers
    )
    assert resp.status_code == 403


def test_manager_cannot_see_all_runs(client, manager_headers):
    resp = client.get("/api/v1/payroll/runs", headers=manager_headers)
    assert resp.status_code == 403


# ----------------------------------------------------------------------- pdf
def test_payslip_pdf_downloads(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    payslips = client.get(
        f"/api/v1/payroll/runs/{run['id']}/payslips", headers=hr_headers
    ).json()
    payslip_id = payslips["items"][0]["id"]

    resp = client.get(
        f"/api/v1/payroll/payslips/{payslip_id}/pdf", headers=hr_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_summary_reports_aggregates(client, hr_headers, org, structure):
    run = _processed_run(client, hr_headers)
    resp = client.get(f"/api/v1/payroll/runs/{run['id']}/summary", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_employees"] == 1
    assert Decimal(body["total_net"]) == Decimal(body["average_net"])
