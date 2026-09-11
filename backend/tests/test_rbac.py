"""Role-based access control tests."""

from tests.conftest import TEST_PASSWORD


def test_employee_cannot_list_users(client, employee_headers):
    resp = client.get("/api/v1/users", headers=employee_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "permission_denied"


def test_manager_can_list_users(client, manager_headers):
    assert client.get("/api/v1/users", headers=manager_headers).status_code == 200


def test_employee_cannot_register_users(client, employee_headers):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "x@test.com", "full_name": "X", "role_name": "employee"},
        headers=employee_headers,
    )
    assert resp.status_code == 403


def test_manager_cannot_register_users(client, manager_headers):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "x@test.com", "full_name": "X", "role_name": "employee"},
        headers=manager_headers,
    )
    assert resp.status_code == 403


def test_hr_cannot_manage_roles(client, hr_headers):
    resp = client.post(
        "/api/v1/roles",
        json={"name": "auditor", "display_name": "Auditor", "hierarchy_level": 3},
        headers=hr_headers,
    )
    assert resp.status_code == 403


def test_admin_can_create_and_delete_a_role(client, admin_headers):
    created = client.post(
        "/api/v1/roles",
        json={
            "name": "auditor",
            "display_name": "Auditor",
            "hierarchy_level": 3,
            "permission_codes": ["audit:read", "report:generate"],
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    role = created.json()
    assert {p["code"] for p in role["permissions"]} == {"audit:read", "report:generate"}

    deleted = client.delete(f"/api/v1/roles/{role['id']}", headers=admin_headers)
    assert deleted.status_code == 200


def test_system_role_cannot_be_deleted(client, admin_headers):
    roles = client.get("/api/v1/roles", headers=admin_headers).json()
    hr_role = next(r for r in roles if r["name"] == "hr")
    resp = client.delete(f"/api/v1/roles/{hr_role['id']}", headers=admin_headers)
    assert resp.status_code == 400


def test_admin_permission_set_is_a_superset_of_hr(client, admin_headers, hr_headers):
    admin_perms = set(client.get("/api/v1/auth/permissions", headers=admin_headers).json()["permissions"])
    hr_perms = set(client.get("/api/v1/auth/permissions", headers=hr_headers).json()["permissions"])
    assert hr_perms < admin_perms


def test_role_hierarchy_narrows_permissions(client, admin_headers, hr_headers, manager_headers, employee_headers):
    def count(headers):
        return len(client.get("/api/v1/auth/permissions", headers=headers).json()["permissions"])

    assert count(admin_headers) > count(hr_headers) > count(manager_headers) > count(employee_headers)


def test_user_cannot_change_own_role(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    resp = client.patch(
        f"/api/v1/users/{me['id']}",
        json={"role_name": "employee"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_user_cannot_deactivate_self(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    resp = client.delete(f"/api/v1/users/{me['id']}", headers=admin_headers)
    assert resp.status_code == 400


def test_deactivated_user_cannot_log_in(client, admin_headers):
    users = client.get("/api/v1/users?search=employee", headers=admin_headers).json()
    target = next(u for u in users["items"] if u["email"] == "employee@test.com")

    assert client.delete(f"/api/v1/users/{target['id']}", headers=admin_headers).status_code == 200

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "employee@test.com", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 401


def test_hr_can_reset_a_password(client, hr_headers, admin_headers):
    users = client.get("/api/v1/users?search=employee", headers=admin_headers).json()
    target = next(u for u in users["items"] if u["email"] == "employee@test.com")

    resp = client.post(
        "/api/v1/auth/reset-password",
        json={"user_id": target["id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 200
    temp = resp.json()["data"]["temporary_password"]

    login = client.post(
        "/api/v1/auth/login", json={"email": "employee@test.com", "password": temp}
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_pagination_metadata_is_present(client, admin_headers):
    resp = client.get("/api/v1/users?page=1&size=2", headers=admin_headers)
    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["page"] == 1 and meta["size"] == 2
    assert meta["total"] == 4 and meta["pages"] == 2
    assert meta["has_next"] is True and meta["has_prev"] is False
