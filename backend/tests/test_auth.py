"""Authentication endpoint tests."""

from tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login"


def test_login_success_returns_tokens_and_profile(client):
    resp = client.post(LOGIN, json={"email": "admin@test.com", "password": TEST_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == "admin@test.com"
    assert body["user"]["role"]["name"] == "admin"
    assert "user:create" in body["user"]["permissions"]


def test_login_wrong_password_is_rejected(client):
    resp = client.post(LOGIN, json={"email": "admin@test.com", "password": "WrongPass1"})
    assert resp.status_code == 401


def test_login_unknown_email_gives_same_message(client):
    unknown = client.post(LOGIN, json={"email": "nobody@test.com", "password": "WrongPass1"})
    wrong = client.post(LOGIN, json={"email": "admin@test.com", "password": "WrongPass1"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_account_locks_after_five_failures(client):
    for _ in range(5):
        client.post(LOGIN, json={"email": "employee@test.com", "password": "Nope12345"})
    resp = client.post(LOGIN, json={"email": "employee@test.com", "password": TEST_PASSWORD})
    assert resp.status_code == 423


def test_me_requires_a_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_rejects_a_garbage_token(client):
    resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert resp.status_code == 401


def test_me_returns_permissions(client, hr_headers):
    resp = client.get("/api/v1/auth/me", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"]["name"] == "hr"
    assert "payroll:process" in body["permissions"]
    assert "system:manage" not in body["permissions"]


def test_refresh_token_returns_new_access_token(client):
    login = client.post(LOGIN, json={"email": "hr@test.com", "password": TEST_PASSWORD})
    refresh = login.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_fails_after_logout(client):
    login = client.post(LOGIN, json={"email": "hr@test.com", "password": TEST_PASSWORD})
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    out = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert out.status_code == 200

    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 401


def test_access_token_is_not_accepted_as_refresh_token(client):
    login = client.post(LOGIN, json={"email": "hr@test.com", "password": TEST_PASSWORD})
    access = login.json()["access_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401


def test_change_password_then_login_with_new_one(client, employee_headers):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "BrandNew456"},
        headers=employee_headers,
    )
    assert resp.status_code == 200

    old = client.post(LOGIN, json={"email": "employee@test.com", "password": TEST_PASSWORD})
    assert old.status_code == 401

    new = client.post(LOGIN, json={"email": "employee@test.com", "password": "BrandNew456"})
    assert new.status_code == 200


def test_change_password_rejects_weak_value(client, employee_headers):
    resp = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "weak"},
        headers=employee_headers,
    )
    assert resp.status_code == 422


def test_register_creates_user_with_temp_password(client, hr_headers):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "newhire@test.com",
            "full_name": "New Hire",
            "role_name": "employee",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "newhire@test.com"
    assert body["user"]["must_change_password"] is True
    assert body["temporary_password"]

    login = client.post(
        LOGIN,
        json={"email": "newhire@test.com", "password": body["temporary_password"]},
    )
    assert login.status_code == 200


def test_register_rejects_duplicate_email(client, hr_headers):
    payload = {"email": "admin@test.com", "full_name": "Clone", "role_name": "employee"}
    resp = client.post("/api/v1/auth/register", json=payload, headers=hr_headers)
    assert resp.status_code == 409
