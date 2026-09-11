"""Attendance and shift tests."""

from datetime import date, datetime, time, timedelta

import pytest

from app.models.attendance import Holiday, Shift
from app.models.enums import AttendanceStatus
from app.services import attendance_service, shift_service


# ------------------------------------------------------- shift hour derivation
def test_day_shift_hours_exclude_break():
    hours, is_night = shift_service.compute_working_hours(time(9, 0), time(18, 0), 60)
    assert hours == 8.0
    assert is_night is False


def test_night_shift_crossing_midnight_is_detected():
    hours, is_night = shift_service.compute_working_hours(time(22, 0), time(6, 0), 60)
    assert hours == 7.0
    assert is_night is True


def test_shift_creation_derives_fields(client, hr_headers):
    resp = client.post(
        "/api/v1/shifts",
        json={
            "code": "NGT",
            "name": "Night Shift",
            "shift_type": "night",
            "start_time": "22:00:00",
            "end_time": "06:00:00",
            "break_minutes": 60,
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_night_shift"] is True
    assert body["working_hours"] == 7.0


# -------------------------------------------------------- attendance date rule
def test_night_shift_early_hours_belong_to_previous_day(db_session):
    shift = Shift(
        code="NGT", name="Night", start_time=time(22, 0), end_time=time(6, 0),
        working_hours=7.0, is_night_shift=True,
    )
    # 00:30 Tuesday is still Monday's shift
    moment = datetime(2026, 3, 10, 0, 30)
    assert attendance_service.attendance_date_for(shift, moment) == date(2026, 3, 9)

    # 22:15 Monday is Monday
    moment = datetime(2026, 3, 9, 22, 15)
    assert attendance_service.attendance_date_for(shift, moment) == date(2026, 3, 9)


def test_day_shift_uses_the_calendar_date(db_session):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, is_night_shift=False,
    )
    moment = datetime(2026, 3, 9, 9, 5)
    assert attendance_service.attendance_date_for(shift, moment) == date(2026, 3, 9)


# ------------------------------------------------------------ check in and out
def test_check_in_then_out_computes_hours(client, employee_headers, org):
    resp = client.post("/api/v1/attendance/check-in", json={}, headers=employee_headers)
    assert resp.status_code == 200
    assert resp.json()["check_in"] is not None

    out = client.post("/api/v1/attendance/check-out", json={}, headers=employee_headers)
    assert out.status_code == 200
    assert out.json()["check_out"] is not None


def test_double_check_in_rejected(client, employee_headers, org):
    client.post("/api/v1/attendance/check-in", json={}, headers=employee_headers)
    second = client.post("/api/v1/attendance/check-in", json={}, headers=employee_headers)
    assert second.status_code == 400
    assert "already checked in" in second.json()["error"]["message"].lower()


def test_check_out_without_check_in_rejected(client, employee_headers, org):
    resp = client.post("/api/v1/attendance/check-out", json={}, headers=employee_headers)
    assert resp.status_code == 400


def test_check_in_requires_an_employee_profile(client, admin_headers):
    resp = client.post("/api/v1/attendance/check-in", json={}, headers=admin_headers)
    assert resp.status_code == 403


def test_late_arrival_flagged_against_grace_period(db_session, org):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, grace_period_minutes=15, is_night_shift=False,
    )
    db_session.add(shift)
    db_session.commit()

    shift_service.assign_shift(
        db_session, shift.id, [org["reportee_id"]], date(2026, 1, 1), None
    )

    record = attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 9, 45)
    )
    assert record.status == AttendanceStatus.LATE
    assert record.late_minutes == 45


def test_arrival_inside_grace_is_not_late(db_session, org):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, grace_period_minutes=15, is_night_shift=False,
    )
    db_session.add(shift)
    db_session.commit()
    shift_service.assign_shift(
        db_session, shift.id, [org["reportee_id"]], date(2026, 1, 1), None
    )

    record = attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 9, 10)
    )
    assert record.status == AttendanceStatus.PRESENT
    assert record.late_minutes == 0


def test_short_day_becomes_half_day(db_session, org):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, break_minutes=60, half_day_threshold_hours=4.0,
        is_night_shift=False,
    )
    db_session.add(shift)
    db_session.commit()
    shift_service.assign_shift(
        db_session, shift.id, [org["reportee_id"]], date(2026, 1, 1), None
    )

    attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 9, 0)
    )
    record = attendance_service.check_out(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 12, 0)
    )
    # 3 hours gross minus a 1 hour break = 2 worked hours
    assert record.worked_hours == 2.0
    assert record.status == AttendanceStatus.HALF_DAY


def test_overtime_computed_beyond_shift_hours(db_session, org):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, break_minutes=60, is_night_shift=False,
    )
    db_session.add(shift)
    db_session.commit()
    shift_service.assign_shift(
        db_session, shift.id, [org["reportee_id"]], date(2026, 1, 1), None
    )

    attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 9, 0)
    )
    record = attendance_service.check_out(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 20, 0)
    )
    # 11 gross - 1 break = 10 worked, 2 over the 8 hour shift
    assert record.worked_hours == 10.0
    assert record.overtime_hours == 2.0


# ----------------------------------------------------------- shift assignment
def test_overlapping_shift_assignment_rejected(client, hr_headers, org, db_session):
    first = client.post(
        "/api/v1/shifts",
        json={"code": "SA", "name": "Shift A", "start_time": "09:00:00", "end_time": "18:00:00"},
        headers=hr_headers,
    ).json()
    second = client.post(
        "/api/v1/shifts",
        json={"code": "SB", "name": "Shift B", "start_time": "14:00:00", "end_time": "22:00:00"},
        headers=hr_headers,
    ).json()

    ok = client.post(
        f"/api/v1/shifts/{first['id']}/assign",
        json={"employee_ids": [org["reportee_id"]], "start_date": "2026-01-01",
              "end_date": "2026-06-30"},
        headers=hr_headers,
    )
    assert ok.status_code == 200

    clash = client.post(
        f"/api/v1/shifts/{second['id']}/assign",
        json={"employee_ids": [org["reportee_id"]], "start_date": "2026-03-01",
              "end_date": "2026-09-30"},
        headers=hr_headers,
    )
    assert clash.status_code == 400
    assert "overlap" in clash.json()["error"]["message"].lower()


def test_non_overlapping_assignment_allowed(client, hr_headers, org):
    first = client.post(
        "/api/v1/shifts",
        json={"code": "SA", "name": "Shift A", "start_time": "09:00:00", "end_time": "18:00:00"},
        headers=hr_headers,
    ).json()
    second = client.post(
        "/api/v1/shifts",
        json={"code": "SB", "name": "Shift B", "start_time": "14:00:00", "end_time": "22:00:00"},
        headers=hr_headers,
    ).json()

    client.post(
        f"/api/v1/shifts/{first['id']}/assign",
        json={"employee_ids": [org["reportee_id"]], "start_date": "2026-01-01",
              "end_date": "2026-03-31"},
        headers=hr_headers,
    )
    later = client.post(
        f"/api/v1/shifts/{second['id']}/assign",
        json={"employee_ids": [org["reportee_id"]], "start_date": "2026-04-01",
              "end_date": "2026-06-30"},
        headers=hr_headers,
    )
    assert later.status_code == 200


# ------------------------------------------------------------- forgotten exit
def test_forgotten_checkout_is_auto_closed(db_session, org):
    shift = Shift(
        code="GEN", name="General", start_time=time(9, 0), end_time=time(18, 0),
        working_hours=8.0, break_minutes=60, is_night_shift=False,
    )
    db_session.add(shift)
    db_session.commit()
    shift_service.assign_shift(
        db_session, shift.id, [org["reportee_id"]], date(2026, 1, 1), None
    )

    attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 9, 9, 0)
    )
    closed = attendance_service.close_forgotten_checkouts(db_session, date(2026, 3, 9))
    assert closed == 1

    from sqlalchemy import select

    from app.models.attendance import Attendance

    record = db_session.execute(
        select(Attendance).where(Attendance.attendance_date == date(2026, 3, 9))
    ).scalar_one()
    assert record.check_out is not None
    assert "auto-closed" in record.remarks


# -------------------------------------------------------------- daily marking
def test_daily_marking_stamps_weekend(db_session, org):
    saturday = date(2026, 3, 14)
    assert saturday.weekday() == 5
    counts = attendance_service.mark_daily_attendance(db_session, saturday)
    assert counts["weekend"] == 4  # every employee in the org fixture


def test_daily_marking_stamps_holiday(db_session, org):
    holiday = date(2026, 3, 11)
    db_session.add(Holiday(name="Founders Day", holiday_date=holiday))
    db_session.commit()

    counts = attendance_service.mark_daily_attendance(db_session, holiday)
    assert counts["holiday"] == 4
    assert counts["absent"] == 0


def test_daily_marking_stamps_absent_on_a_working_day(db_session, org):
    tuesday = date(2026, 3, 10)
    assert tuesday.weekday() == 1
    counts = attendance_service.mark_daily_attendance(db_session, tuesday)
    assert counts["absent"] == 4


def test_daily_marking_does_not_overwrite_existing(db_session, org):
    day = date(2026, 3, 10)
    attendance_service.check_in(
        db_session, org["reportee_id"], moment=datetime(2026, 3, 10, 9, 0)
    )
    counts = attendance_service.mark_daily_attendance(db_session, day)
    assert counts["absent"] == 3  # the checked-in employee is untouched


# ------------------------------------------------------------- working days
def test_working_days_exclude_weekends(db_session):
    # Mon 9 Mar to Sun 15 Mar 2026 = 5 working days
    assert attendance_service.working_days_between(
        db_session, date(2026, 3, 9), date(2026, 3, 15)
    ) == 5


def test_working_days_exclude_holidays(db_session):
    db_session.add(Holiday(name="Festival", holiday_date=date(2026, 3, 11)))
    db_session.commit()
    assert attendance_service.working_days_between(
        db_session, date(2026, 3, 9), date(2026, 3, 15)
    ) == 4


# -------------------------------------------------------------- regularisation
def test_regularization_requires_approval_then_updates_status(client, hr_headers, employee_headers, org):
    ask = client.post(
        "/api/v1/attendance/regularize",
        json={
            "attendance_date": "2026-03-09",
            "check_in": "2026-03-09T09:00:00",
            "check_out": "2026-03-09T18:00:00",
            "reason": "Forgot to badge in at reception",
        },
        headers=employee_headers,
    )
    assert ask.status_code == 200
    assert ask.json()["regularization_status"] == "pending"

    record_id = ask.json()["id"]
    decision = client.post(
        f"/api/v1/attendance/{record_id}/regularization",
        json={"approve": True},
        headers=hr_headers,
    )
    assert decision.status_code == 200
    assert decision.json()["regularization_status"] == "approved"


def test_future_regularization_rejected(client, employee_headers, org):
    future = (date.today() + timedelta(days=5)).isoformat()
    resp = client.post(
        "/api/v1/attendance/regularize",
        json={"attendance_date": future, "reason": "Planning ahead"},
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_employee_cannot_approve_regularizations(client, employee_headers, org):
    ask = client.post(
        "/api/v1/attendance/regularize",
        json={"attendance_date": "2026-03-09", "reason": "Badge failure"},
        headers=employee_headers,
    ).json()
    resp = client.post(
        f"/api/v1/attendance/{ask['id']}/regularization",
        json={"approve": True},
        headers=employee_headers,
    )
    assert resp.status_code == 403


# -------------------------------------------------------------------- summary
def test_summary_reports_attendance_percent(client, hr_headers, org, db_session):
    for day in [date(2026, 3, 9), date(2026, 3, 10)]:
        attendance_service.check_in(
            db_session, org["reportee_id"],
            moment=datetime(day.year, day.month, day.day, 9, 0),
        )
        attendance_service.check_out(
            db_session, org["reportee_id"],
            moment=datetime(day.year, day.month, day.day, 18, 0),
        )

    resp = client.get(
        f"/api/v1/attendance/summary/{org['reportee_id']}"
        "?start=2026-03-09&end=2026-03-13",
        headers=hr_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["working_days"] == 5
    assert body["present_days"] == 2.0
    assert body["attendance_percent"] == 40.0
