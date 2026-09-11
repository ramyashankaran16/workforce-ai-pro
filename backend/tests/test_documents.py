"""Notification, chat, document, dashboard and monitoring tests."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.document import DocumentCategory
from app.models.enums import DocumentStatus, DocumentVisibility
from app.services import document_service, notification_service
from app.utils import file_handler

PDF = b"%PDF-1.4\n%fake pdf content for testing\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


@pytest.fixture
def categories(db_session):
    id_proof = DocumentCategory(
        code="IDPROOF", name="Identity Proof", is_mandatory=True,
        requires_expiry=True, allowed_extensions="pdf,jpg,png", max_size_mb=5,
    )
    certificate = DocumentCategory(
        code="EDU", name="Educational Certificate", is_mandatory=True,
        allowed_extensions="pdf", max_size_mb=5,
    )
    db_session.add_all([id_proof, certificate])
    db_session.commit()
    return {"id_proof": id_proof.id, "certificate": certificate.id}


def _upload(client, headers, content=PDF, filename="passport.pdf",
            title="Passport", **extra):
    data = {"title": title}
    data.update({k: str(v) for k, v in extra.items() if v is not None})
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/pdf")},
        data=data,
        headers=headers,
    )


# ------------------------------------------------------------ file validation
def test_magic_bytes_reject_a_renamed_file():
    with pytest.raises(Exception) as exc:
        file_handler.validate_upload(
            b"#!/bin/bash\nrm -rf /", "script.pdf", {"pdf"}, 5
        )
    assert "does not match" in str(exc.value.detail)


def test_blocked_extension_rejected():
    with pytest.raises(Exception) as exc:
        file_handler.validate_upload(b"MZ", "malware.exe", {"exe"}, 5)
    assert "not accepted" in str(exc.value.detail)


def test_double_extension_rejected():
    with pytest.raises(Exception) as exc:
        file_handler.validate_upload(PDF, "report.exe.pdf", {"pdf"}, 5)
    assert "blocked extension" in str(exc.value.detail)


def test_oversized_file_rejected():
    with pytest.raises(Exception) as exc:
        file_handler.validate_upload(PDF + b"x" * (6 * 1024 * 1024), "big.pdf",
                                     {"pdf"}, 5)
    assert "limit is 5 MB" in str(exc.value.detail)


def test_valid_pdf_accepted():
    assert file_handler.validate_upload(PDF, "ok.pdf", {"pdf"}, 5) == "pdf"


def test_filename_is_sanitised():
    assert "/" not in file_handler.safe_filename("../../etc/passwd")
    assert file_handler.safe_filename("my file (1).pdf") == "my_file__1_.pdf"


# -------------------------------------------------------------------- uploads
def test_employee_uploads_against_own_record(client, employee_headers, org):
    resp = _upload(client, employee_headers)
    assert resp.status_code == 201
    assert resp.json()["employee_id"] == org["reportee_id"]
    assert resp.json()["status"] == "pending"


def test_employee_cannot_upload_for_someone_else(client, employee_headers, org):
    resp = _upload(client, employee_headers, employee_id=org["outsider_id"])
    assert resp.status_code == 403


def test_hr_can_upload_for_another_employee(client, hr_headers, org):
    resp = _upload(client, hr_headers, employee_id=org["outsider_id"])
    assert resp.status_code == 201
    assert resp.json()["employee_id"] == org["outsider_id"]


def test_category_requiring_expiry_enforced(client, employee_headers, org, categories):
    resp = _upload(client, employee_headers, category_id=categories["id_proof"])
    assert resp.status_code == 400
    assert "expiry" in resp.json()["error"]["message"].lower()


def test_category_extension_restriction_enforced(
    client, employee_headers, org, categories
):
    resp = _upload(
        client, employee_headers, content=PNG, filename="degree.png",
        category_id=categories["certificate"],
    )
    assert resp.status_code == 422


def test_reupload_increments_the_version(client, employee_headers, org, categories):
    expiry = (date.today() + timedelta(days=400)).isoformat()
    first = _upload(client, employee_headers, category_id=categories["id_proof"],
                    expiry_date=expiry)
    second = _upload(client, employee_headers, category_id=categories["id_proof"],
                     expiry_date=expiry, title="Passport renewed")
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2


# ---------------------------------------------------------------- verification
def test_hr_verifies_a_document(client, employee_headers, hr_headers, org):
    document = _upload(client, employee_headers).json()
    resp = client.post(
        f"/api/v1/documents/{document['id']}/verify",
        json={"approve": True},
        headers=hr_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"


def test_rejection_requires_a_reason(client, employee_headers, hr_headers, org):
    document = _upload(client, employee_headers).json()
    resp = client.post(
        f"/api/v1/documents/{document['id']}/verify",
        json={"approve": False},
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_employee_cannot_verify(client, employee_headers, org):
    document = _upload(client, employee_headers).json()
    resp = client.post(
        f"/api/v1/documents/{document['id']}/verify",
        json={"approve": True},
        headers=employee_headers,
    )
    assert resp.status_code == 403


def test_verification_notifies_the_owner(
    client, employee_headers, hr_headers, org, db_session
):
    document = _upload(client, employee_headers).json()
    client.post(
        f"/api/v1/documents/{document['id']}/verify",
        json={"approve": True},
        headers=hr_headers,
    )
    notifications = client.get(
        "/api/v1/notifications?unread_only=true", headers=employee_headers
    ).json()
    titles = [n["title"] for n in notifications["items"]]
    assert any("verified" in t.lower() for t in titles)


# -------------------------------------------------------------------- access
def test_private_document_hidden_from_the_manager(
    client, employee_headers, manager_headers, org
):
    document = _upload(client, employee_headers, visibility="private").json()
    resp = client.get(f"/api/v1/documents/{document['id']}", headers=manager_headers)
    assert resp.status_code == 403


def test_manager_visibility_lets_the_manager_read(
    client, employee_headers, manager_headers, org
):
    document = _upload(client, employee_headers, visibility="manager").json()
    resp = client.get(f"/api/v1/documents/{document['id']}", headers=manager_headers)
    assert resp.status_code == 200


def test_hr_reads_regardless_of_visibility(client, employee_headers, hr_headers, org):
    document = _upload(client, employee_headers, visibility="private").json()
    resp = client.get(f"/api/v1/documents/{document['id']}", headers=hr_headers)
    assert resp.status_code == 200


def test_download_is_permission_checked(
    client, employee_headers, manager_headers, org
):
    document = _upload(client, employee_headers, visibility="private").json()
    assert client.get(
        f"/api/v1/documents/{document['id']}/download", headers=manager_headers
    ).status_code == 403
    ok = client.get(
        f"/api/v1/documents/{document['id']}/download", headers=employee_headers
    )
    assert ok.status_code == 200


# ------------------------------------------------------------------- expiry
def test_expiring_documents_listed(client, employee_headers, hr_headers, org, categories):
    soon = (date.today() + timedelta(days=10)).isoformat()
    _upload(client, employee_headers, category_id=categories["id_proof"],
            expiry_date=soon)
    resp = client.get("/api/v1/documents/expiring?days=30", headers=hr_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["days_remaining"] <= 30


def test_expired_documents_flagged(client, employee_headers, org, db_session, categories):
    from app.models.document import Document

    expiry = (date.today() + timedelta(days=30)).isoformat()
    document = _upload(client, employee_headers, category_id=categories["id_proof"],
                       expiry_date=expiry).json()

    row = db_session.get(Document, document["id"])
    row.expiry_date = date.today() - timedelta(days=1)
    db_session.commit()

    flagged = document_service.flag_expired(db_session)
    assert flagged == 1
    db_session.refresh(row)
    assert row.status == DocumentStatus.EXPIRED


def test_compliance_lists_missing_mandatory(client, hr_headers, org, categories):
    resp = client.get(
        f"/api/v1/documents/compliance/{org['reportee_id']}", headers=hr_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_compliant"] is False
    assert "Identity Proof" in body["missing_mandatory"]


# ------------------------------------------------------------- notifications
def test_unread_count_and_mark_read(client, employee_headers, hr_headers, org, db_session):
    _upload(client, employee_headers)
    count = client.get("/api/v1/notifications/count", headers=hr_headers).json()
    assert count["unread"] >= 1

    notifications = client.get("/api/v1/notifications", headers=hr_headers).json()
    first = notifications["items"][0]
    client.post(f"/api/v1/notifications/{first['id']}/read", headers=hr_headers)

    after = client.get("/api/v1/notifications/count", headers=hr_headers).json()
    assert after["unread"] == count["unread"] - 1


def test_mark_all_read(client, employee_headers, hr_headers, org):
    _upload(client, employee_headers)
    client.post("/api/v1/notifications/read-all", headers=hr_headers)
    after = client.get("/api/v1/notifications/count", headers=hr_headers).json()
    assert after["unread"] == 0


def test_preferences_default_then_update(client, employee_headers):
    defaults = client.get(
        "/api/v1/notifications/preferences", headers=employee_headers
    ).json()
    assert all(p["in_app_enabled"] for p in defaults)
    assert not any(p["sms_enabled"] for p in defaults)

    resp = client.put(
        "/api/v1/notifications/preferences",
        json={
            "preferences": [
                {"category": "payroll", "in_app_enabled": False,
                 "email_enabled": False, "sms_enabled": False}
            ]
        },
        headers=employee_headers,
    )
    assert resp.status_code == 200
    payroll = next(p for p in resp.json() if p["category"] == "payroll")
    assert payroll["in_app_enabled"] is False


def test_muted_category_is_not_delivered(client, employee_headers, org, db_session):
    client.put(
        "/api/v1/notifications/preferences",
        json={
            "preferences": [
                {"category": "document", "in_app_enabled": False,
                 "email_enabled": False, "sms_enabled": False}
            ]
        },
        headers=employee_headers,
    )
    before = client.get("/api/v1/notifications/count", headers=employee_headers).json()

    from app.models.employee import Employee

    employee = db_session.get(Employee, org["reportee_id"])
    sent = notification_service.notify(
        db_session,
        employee.user_id,
        title="Document update",
        message="Ignored",
        category=__import__(
            "app.models.enums", fromlist=["NotificationCategory"]
        ).NotificationCategory.DOCUMENT,
    )
    assert sent is None

    after = client.get("/api/v1/notifications/count", headers=employee_headers).json()
    assert after["unread"] == before["unread"]


def test_broadcast_requires_system_manage(client, hr_headers, admin_headers):
    payload = {"roles": ["employee"], "title": "Office closed",
               "message": "The office is closed on Friday."}
    assert client.post(
        "/api/v1/notifications/broadcast", json=payload, headers=hr_headers
    ).status_code == 403
    assert client.post(
        "/api/v1/notifications/broadcast", json=payload, headers=admin_headers
    ).status_code == 200


# --------------------------------------------------------------------- chat
def test_conversation_is_idempotent(client, employee_headers, manager_headers, db_session, org):
    from app.models.user import User

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()

    first = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()
    second = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()
    assert first["id"] == second["id"]


def test_reverse_pair_resolves_to_the_same_thread(
    client, employee_headers, manager_headers, db_session
):
    from app.models.user import User

    employee_user = db_session.execute(
        select(User).where(User.email == "employee@test.com")
    ).scalar_one()
    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()

    forward = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()
    reverse = client.post(
        "/api/v1/chat/conversations", json={"user_id": employee_user.id},
        headers=manager_headers,
    ).json()
    assert forward["id"] == reverse["id"]


def test_cannot_message_yourself(client, employee_headers, db_session):
    from app.models.user import User

    me = db_session.execute(
        select(User).where(User.email == "employee@test.com")
    ).scalar_one()
    resp = client.post(
        "/api/v1/chat/conversations", json={"user_id": me.id},
        headers=employee_headers,
    )
    assert resp.status_code == 400


def test_send_and_read_a_message(client, employee_headers, manager_headers, db_session):
    from app.models.user import User

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    conversation = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()

    sent = client.post(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        json={"content": "Could we discuss my leave request?"},
        headers=employee_headers,
    )
    assert sent.status_code == 201

    threads = client.get("/api/v1/chat/conversations", headers=manager_headers).json()
    assert threads[0]["unread_count"] == 1

    client.post(
        f"/api/v1/chat/conversations/{conversation['id']}/read", headers=manager_headers
    )
    threads = client.get("/api/v1/chat/conversations", headers=manager_headers).json()
    assert threads[0]["unread_count"] == 0


def test_outsider_cannot_read_a_thread(
    client, employee_headers, manager_headers, admin_headers, db_session
):
    from app.models.user import User

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    conversation = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()

    resp = client.get(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        headers=admin_headers,
    )
    assert resp.status_code == 403


def test_only_the_sender_can_edit(client, employee_headers, manager_headers, db_session):
    from app.models.user import User

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    conversation = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()
    message = client.post(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        json={"content": "Original text"},
        headers=employee_headers,
    ).json()

    assert client.patch(
        f"/api/v1/chat/messages/{message['id']}",
        json={"content": "Edited by someone else"},
        headers=manager_headers,
    ).status_code == 403

    edited = client.patch(
        f"/api/v1/chat/messages/{message['id']}",
        json={"content": "Edited text"},
        headers=employee_headers,
    )
    assert edited.status_code == 200
    assert edited.json()["is_edited"] is True


def test_deleted_message_is_soft_deleted(
    client, employee_headers, manager_headers, db_session
):
    from app.models.user import User

    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    conversation = client.post(
        "/api/v1/chat/conversations", json={"user_id": manager_user.id},
        headers=employee_headers,
    ).json()
    message = client.post(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        json={"content": "Sent by mistake"},
        headers=employee_headers,
    ).json()

    client.delete(f"/api/v1/chat/messages/{message['id']}", headers=employee_headers)

    messages = client.get(
        f"/api/v1/chat/conversations/{conversation['id']}/messages",
        headers=manager_headers,
    ).json()
    assert messages["items"][0]["content"] == "[message deleted]"
    assert messages["items"][0]["is_deleted"] is True


# ---------------------------------------------------------------- dashboard
def test_employee_dashboard_has_only_a_personal_section(client, employee_headers, org):
    resp = client.get("/api/v1/dashboard", headers=employee_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "employee"
    assert "me" in body
    assert "organisation" not in body
    assert "team" not in body


def test_manager_dashboard_is_scoped_to_the_team(client, manager_headers, org):
    body = client.get("/api/v1/dashboard", headers=manager_headers).json()
    assert body["role"] == "manager"
    assert "team" in body
    assert body["team"]["headcount"] == 1  # one reportee
    assert "organisation" not in body


def test_hr_dashboard_covers_the_organisation(client, hr_headers, org):
    body = client.get("/api/v1/dashboard", headers=hr_headers).json()
    assert body["role"] == "hr"
    assert "organisation" in body
    assert body["organisation"]["headcount"] == 4
    assert "risk_distribution" in body


def test_headcount_breakdown_groups_correctly(client, hr_headers, org):
    body = client.get("/api/v1/dashboard/headcount", headers=hr_headers).json()
    assert body["total"] == 4
    assert "Engineering" in body["by_department"]


# --------------------------------------------------------------- monitoring
def test_live_snapshot_adds_up(client, hr_headers, org):
    body = client.get("/api/v1/monitoring/live", headers=hr_headers).json()
    assert body["headcount"] == 4
    assert "as_of" in body


def test_presence_lists_checked_in_staff(client, employee_headers, hr_headers, org):
    client.post("/api/v1/attendance/check-in", json={}, headers=employee_headers)
    presence = client.get("/api/v1/monitoring/presence", headers=hr_headers).json()
    assert len(presence) == 1
    assert presence[0]["employee_code"] == "EMP0003"
