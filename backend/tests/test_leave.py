"""Leave balance, application and approval tests."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.attendance import Holiday
from app.models.enums import LeaveDuration, LeaveStatus
from app.models.leave import LeaveBalance, LeaveType
from app.services import leave_service


@pytest.fixture
def leave_types(db_session):
    casual = LeaveType(code="CL", name="Casual Leave", annual_quota=12.0, is_paid=True)
    earned = LeaveType(
        code="EL", name="Earned Leave", annual_quota=15.0, is_paid=True,
        is_carry_forward=True, max_carry_forward=10.0,
    )
    sick = LeaveType(
        code="SL", name="Sick Leave", annual_quota=12.0, is_paid=True,
        requires_document=True,
    )
    unpaid = LeaveType(code="LOP", name="Loss of Pay", annual_quota=0.0, is_paid=False)
    notice = LeaveType(
        code="PL", name="Planned Leave", annual_quota=10.0, is_paid=True,
        min_notice_days=7,
    )
    capped = LeaveType(
        code="CO", name="Comp Off", annual_quota=5.0, is_paid=True,
        max_consecutive_days=2,
    )
    db_session.add_all([casual, earned, sick, unpaid, notice, capped])
    db_session.commit()
    return {
        "casual": casual.id, "earned": earned.id, "sick": sick.id,
        "unpaid": unpaid.id, "notice": notice.id, "capped": capped.id,
    }


def _future(days: int) -> str:
    """
    A future date guaranteed to be a weekday.

    Weekends carry no chargeable days, so a naive offset would randomly land on
    a Saturday and make these tests fail depending on the day they run.
    """
    day = date.today() + timedelta(days=days)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def _next_monday() -> date:
    """A fixed weekday anchor, so Monday and Tuesday are always distinct dates."""
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


# ------------------------------------------------------------ day calculation
def test_weekend_days_are_not_charged(db_session, leave_types):
    # Fri 13 Mar to Mon 16 Mar 2026 -> Fri + Mon = 2 days
    days = leave_service.countable_days(
        db_session, date(2026, 3, 13), date(2026, 3, 16), LeaveDuration.FULL_DAY
    )
    assert days == 2


def test_holidays_are_not_charged(db_session, leave_types):
    db_session.add(Holiday(name="Festival", holiday_date=date(2026, 3, 11)))
    db_session.commit()
    # Mon 9 to Fri 13 March, with Wednesday a holiday -> 4 days
    days = leave_service.countable_days(
        db_session, date(2026, 3, 9), date(2026, 3, 13), LeaveDuration.FULL_DAY
    )
    assert days == 4


def test_half_day_charges_half(db_session, leave_types):
    days = leave_service.countable_days(
        db_session, date(2026, 3, 9), date(2026, 3, 9), LeaveDuration.FIRST_HALF
    )
    assert days == 0.5


# -------------------------------------------------------------------- balance
def test_balance_created_on_first_read(client, employee_headers, org, leave_types):
    resp = client.get("/api/v1/leaves/balance", headers=employee_headers)
    assert resp.status_code == 200
    balances = {b["leave_type_code"]: b for b in resp.json()}
    assert balances["CL"]["allocated"] == 12.0
    assert balances["CL"]["available"] == 12.0


def test_applying_moves_days_to_pending(client, employee_headers, org, leave_types):
    apply = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Family function",
        },
        headers=employee_headers,
    )
    assert apply.status_code == 201

    balances = {
        b["leave_type_code"]: b
        for b in client.get("/api/v1/leaves/balance", headers=employee_headers).json()
    }
    assert balances["CL"]["pending"] == 1.0
    assert balances["CL"]["used"] == 0.0
    assert balances["CL"]["available"] == 11.0


def test_approval_moves_pending_to_used(client, employee_headers, hr_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Family function",
        },
        headers=employee_headers,
    ).json()

    approve = client.post(
        f"/api/v1/leaves/{request['id']}/approve",
        json={"remarks": "Approved"},
        headers=hr_headers,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    balances = {
        b["leave_type_code"]: b
        for b in client.get("/api/v1/leaves/balance", headers=employee_headers).json()
    }
    assert balances["CL"]["pending"] == 0.0
    assert balances["CL"]["used"] == 1.0
    assert balances["CL"]["available"] == 11.0


def test_rejection_releases_the_reservation(client, employee_headers, hr_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Personal errand",
        },
        headers=employee_headers,
    ).json()

    client.post(
        f"/api/v1/leaves/{request['id']}/reject",
        json={"remarks": "Critical delivery week"},
        headers=hr_headers,
    )

    balances = {
        b["leave_type_code"]: b
        for b in client.get("/api/v1/leaves/balance", headers=employee_headers).json()
    }
    assert balances["CL"]["pending"] == 0.0
    assert balances["CL"]["used"] == 0.0
    assert balances["CL"]["available"] == 12.0


def test_cancelling_releases_the_reservation(client, employee_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Changed my mind later",
        },
        headers=employee_headers,
    ).json()

    cancel = client.post(
        f"/api/v1/leaves/{request['id']}/cancel", headers=employee_headers
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    balances = {
        b["leave_type_code"]: b
        for b in client.get("/api/v1/leaves/balance", headers=employee_headers).json()
    }
    assert balances["CL"]["available"] == 12.0


def test_insufficient_balance_rejected(client, employee_headers, org, leave_types):
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["capped"],  # 5 day quota, 2 day max run
            "start_date": _future(10),
            "end_date": _future(40),
            "reason": "Extended personal break",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_pending_request_blocks_a_second_overlapping_one(client, employee_headers, org, leave_types):
    first = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(12),
            "reason": "First request",
        },
        headers=employee_headers,
    )
    assert first.status_code == 201

    overlap = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["earned"],
            "start_date": _future(11),
            "end_date": _future(13),
            "reason": "Overlapping request",
        },
        headers=employee_headers,
    )
    assert overlap.status_code == 400
    assert "overlap" in overlap.json()["error"]["message"].lower()


def test_unpaid_leave_ignores_balance(client, employee_headers, org, leave_types):
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["unpaid"],  # zero quota
            "start_date": _future(10),
            "end_date": _future(11),
            "reason": "Unpaid personal time",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 201


# --------------------------------------------------------------- policy rules
def test_notice_period_enforced(client, employee_headers, org, leave_types):
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["notice"],  # needs 7 days notice
            "start_date": _future(2),
            "end_date": _future(2),
            "reason": "Short notice request",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "notice" in resp.json()["error"]["message"].lower()


def test_document_requirement_enforced(client, employee_headers, org, leave_types):
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["sick"],
            "start_date": _future(1),
            "end_date": _future(1),
            "reason": "Unwell, seeing a doctor",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "document" in resp.json()["error"]["message"].lower()


def test_max_consecutive_days_enforced(client, employee_headers, org, leave_types):
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["capped"],  # max 2 consecutive
            "start_date": _future(10),
            "end_date": _future(16),
            "reason": "Long comp off run",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "consecutive" in resp.json()["error"]["message"].lower()


def test_weekend_only_range_rejected(client, employee_headers, org, leave_types):
    # find the next Saturday
    today = date.today()
    saturday = today + timedelta(days=(5 - today.weekday()) % 7 + 7)
    sunday = saturday + timedelta(days=1)

    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": saturday.isoformat(),
            "end_date": sunday.isoformat(),
            "reason": "Weekend only request",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 400
    assert "working day" in resp.json()["error"]["message"].lower()


def test_half_day_across_two_dates_rejected(client, employee_headers, org, leave_types):
    monday = _next_monday()
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(days=1)).isoformat(),
            "duration": "first_half",
            "reason": "Half day spanning two dates",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422


def test_end_before_start_rejected(client, employee_headers, org, leave_types):
    monday = _next_monday()
    resp = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": (monday + timedelta(days=1)).isoformat(),
            "end_date": monday.isoformat(),
            "reason": "Backwards range",
        },
        headers=employee_headers,
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------- approval
def test_manager_can_approve_their_reportee(client, employee_headers, manager_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Family event",
        },
        headers=employee_headers,
    ).json()

    resp = client.post(
        f"/api/v1/leaves/{request['id']}/approve",
        json={"remarks": "Fine"},
        headers=manager_headers,
    )
    assert resp.status_code == 200


def test_pending_queue_shows_only_own_reportees(client, employee_headers, manager_headers, org, leave_types):
    client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Family event",
        },
        headers=employee_headers,
    )
    queue = client.get("/api/v1/leaves/pending", headers=manager_headers)
    assert queue.status_code == 200
    assert queue.json()["meta"]["total"] == 1


def test_employee_cannot_approve(client, employee_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Self approval attempt",
        },
        headers=employee_headers,
    ).json()

    resp = client.post(
        f"/api/v1/leaves/{request['id']}/approve", json={}, headers=employee_headers
    )
    assert resp.status_code == 403


def test_already_decided_request_cannot_be_approved_twice(client, employee_headers, hr_headers, org, leave_types):
    request = client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": leave_types["casual"],
            "start_date": _future(10),
            "end_date": _future(10),
            "reason": "Double approval",
        },
        headers=employee_headers,
    ).json()

    client.post(f"/api/v1/leaves/{request['id']}/approve", json={}, headers=hr_headers)
    second = client.post(
        f"/api/v1/leaves/{request['id']}/approve", json={}, headers=hr_headers
    )
    assert second.status_code == 400


# -------------------------------------------------------------- carry forward
def test_carry_forward_caps_at_max(client, hr_headers, db_session, org, leave_types):
    balance = leave_service.get_or_create_balance(
        db_session, org["reportee_id"], leave_types["earned"], 2025
    )
    balance.allocated = 15.0
    balance.used = 2.0  # 13 remaining, cap is 10
    db_session.commit()

    resp = client.post("/api/v1/leaves/carry-forward?from_year=2025", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json()["total_days_carried"] == 10.0

    new_balance = db_session.execute(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == org["reportee_id"],
            LeaveBalance.leave_type_id == leave_types["earned"],
            LeaveBalance.year == 2026,
        )
    ).scalar_one()
    assert new_balance.carried_forward == 10.0


def test_non_carry_forward_type_lapses(client, hr_headers, db_session, org, leave_types):
    balance = leave_service.get_or_create_balance(
        db_session, org["reportee_id"], leave_types["casual"], 2025
    )
    balance.allocated = 12.0
    db_session.commit()

    client.post("/api/v1/leaves/carry-forward?from_year=2025", headers=hr_headers)

    carried = db_session.execute(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == org["reportee_id"],
            LeaveBalance.leave_type_id == leave_types["casual"],
            LeaveBalance.year == 2026,
        )
    ).scalar_one_or_none()
    assert carried is None or carried.carried_forward == 0.0
