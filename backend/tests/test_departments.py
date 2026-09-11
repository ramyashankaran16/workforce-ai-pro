"""Department and designation tests."""


def test_hr_can_create_a_department(client, hr_headers):
    resp = client.post(
        "/api/v1/departments",
        json={"code": "OPS", "name": "Operations", "location": "Salem"},
        headers=hr_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["code"] == "OPS"


def test_department_code_is_uppercased(client, hr_headers):
    resp = client.post(
        "/api/v1/departments",
        json={"code": "FIN", "name": "Finance"},
        headers=hr_headers,
    )
    assert resp.json()["code"] == "FIN"


def test_duplicate_department_code_rejected(client, hr_headers, org):
    resp = client.post(
        "/api/v1/departments",
        json={"code": "ENG", "name": "Engineering Again"},
        headers=hr_headers,
    )
    assert resp.status_code == 409


def test_employee_cannot_create_a_department(client, employee_headers):
    resp = client.post(
        "/api/v1/departments",
        json={"code": "XYZ", "name": "Nope"},
        headers=employee_headers,
    )
    assert resp.status_code == 403


def test_department_detail_includes_headcount(client, hr_headers, org):
    resp = client.get(f"/api/v1/departments/{org['eng_id']}", headers=hr_headers)
    assert resp.status_code == 200
    # Meera and Eshan are both in Engineering
    assert resp.json()["headcount"] == 2


def test_department_cannot_be_its_own_parent(client, hr_headers, org):
    resp = client.patch(
        f"/api/v1/departments/{org['eng_id']}",
        json={"parent_id": org["eng_id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_department_cycle_is_rejected(client, hr_headers, org):
    # make HR a child of Engineering
    first = client.patch(
        f"/api/v1/departments/{org['hr_dept_id']}",
        json={"parent_id": org["eng_id"]},
        headers=hr_headers,
    )
    assert first.status_code == 200

    # now try to make Engineering a child of HR -> cycle
    resp = client.patch(
        f"/api/v1/departments/{org['eng_id']}",
        json={"parent_id": org["hr_dept_id"]},
        headers=hr_headers,
    )
    assert resp.status_code == 400
    assert "cycle" in resp.json()["error"]["message"].lower()


def test_department_with_employees_cannot_be_deleted(client, hr_headers, org):
    resp = client.delete(f"/api/v1/departments/{org['eng_id']}", headers=hr_headers)
    assert resp.status_code == 400
    assert "employee" in resp.json()["error"]["message"].lower()


def test_empty_department_can_be_deleted(client, hr_headers):
    created = client.post(
        "/api/v1/departments",
        json={"code": "TEMP", "name": "Temporary"},
        headers=hr_headers,
    ).json()
    resp = client.delete(f"/api/v1/departments/{created['id']}", headers=hr_headers)
    assert resp.status_code == 200


def test_department_tree_nests_children(client, hr_headers, org):
    client.patch(
        f"/api/v1/departments/{org['hr_dept_id']}",
        json={"parent_id": org["eng_id"]},
        headers=hr_headers,
    )
    tree = client.get("/api/v1/departments/tree", headers=hr_headers).json()
    roots = {n["code"]: n for n in tree}
    assert "ENG" in roots
    assert [c["code"] for c in roots["ENG"]["children"]] == ["HR"]


def test_designation_salary_band_validated(client, hr_headers):
    resp = client.post(
        "/api/v1/designations",
        json={"title": "Architect", "level": 5, "min_salary": 900000, "max_salary": 500000},
        headers=hr_headers,
    )
    assert resp.status_code == 400


def test_designation_in_use_cannot_be_deleted(client, hr_headers, org):
    resp = client.delete(f"/api/v1/designations/{org['senior_id']}", headers=hr_headers)
    assert resp.status_code == 400
