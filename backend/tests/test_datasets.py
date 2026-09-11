"""Dataset upload, profiling and validation tests."""

import io

import pytest

CSV = (
    "Age,Department,MonthlyIncome,YearsAtCompany,OverTime,Attrition\n"
    "35,Sales,5200,7,No,No\n"
    "29,Engineering,7400,3,Yes,Yes\n"
    "41,Engineering,9100,12,No,No\n"
    "24,Sales,3300,1,Yes,Yes\n"
    "38,Finance,6800,9,No,No\n"
)


def _upload(client, headers, content=CSV, name="IBM HR", target="Attrition",
            filename="hr.csv"):
    data = {"name": name}
    if target is not None:
        data["target_column"] = target
    return client.post(
        "/api/v1/datasets/upload",
        files={"file": (filename, content, "text/csv")},
        data=data,
        headers=headers,
    )


def test_upload_profiles_every_column(client, hr_headers):
    resp = _upload(client, hr_headers)
    assert resp.status_code == 201
    body = resp.json()

    assert body["total_rows"] == 5
    assert body["total_columns"] == 6
    assert body["target_column"] == "Attrition"
    assert len(body["columns"]) == 6

    by_name = {c["name"]: c for c in body["columns"]}
    assert by_name["Age"]["data_type"] == "numeric"
    assert by_name["Age"]["mean_value"] == pytest.approx(33.4, abs=0.1)
    assert by_name["Department"]["data_type"] == "categorical"
    assert by_name["Department"]["top_categories"]["Engineering"] == 2


def test_target_marked_and_excluded_from_features(client, hr_headers):
    body = _upload(client, hr_headers).json()
    target = next(c for c in body["columns"] if c["name"] == "Attrition")
    assert target["is_target"] is True
    assert target["is_feature"] is False


def test_positive_class_ratio_computed_from_yes_no(client, hr_headers):
    body = _upload(client, hr_headers).json()
    assert body["positive_class_ratio"] == 0.4  # 2 of 5


def test_unknown_target_column_rejected(client, hr_headers):
    resp = _upload(client, hr_headers, target="NotAColumn")
    assert resp.status_code == 422


def test_non_tabular_file_rejected(client, hr_headers):
    resp = _upload(client, hr_headers, content="x", filename="notes.txt")
    assert resp.status_code == 422


def test_preview_returns_rows(client, hr_headers):
    dataset = _upload(client, hr_headers).json()
    resp = client.get(
        f"/api/v1/datasets/{dataset['id']}/preview?rows=3", headers=hr_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 3
    assert body["total_rows"] == 5
    assert "Attrition" in body["columns"]


def test_validation_warns_about_small_datasets(client, hr_headers):
    dataset = _upload(client, hr_headers).json()
    resp = client.post(
        f"/api/v1/datasets/{dataset['id']}/validate", headers=hr_headers
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["valid"] is True
    assert any("rows" in w for w in report["warnings"])


def test_validation_fails_on_a_single_class_target(client, hr_headers):
    content = (
        "Age,Attrition\n30,No\n31,No\n32,No\n33,No\n"
    )
    dataset = _upload(client, hr_headers, content=content).json()
    resp = client.post(
        f"/api/v1/datasets/{dataset['id']}/validate", headers=hr_headers
    )
    report = resp.json()
    assert report["valid"] is False
    assert any("one class" in e for e in report["errors"])


def test_validation_fails_on_a_non_binary_target(client, hr_headers):
    content = (
        "Age,Attrition\n30,Maybe\n31,Possibly\n32,Unclear\n33,Perhaps\n"
    )
    dataset = _upload(client, hr_headers, content=content).json()
    report = client.post(
        f"/api/v1/datasets/{dataset['id']}/validate", headers=hr_headers
    ).json()
    assert report["valid"] is False
    assert any("not binary" in e for e in report["errors"])


def test_validation_flags_a_constant_column(client, hr_headers):
    content = (
        "Age,Country,Attrition\n30,India,No\n31,India,Yes\n"
        "32,India,No\n33,India,Yes\n"
    )
    dataset = _upload(client, hr_headers, content=content).json()
    report = client.post(
        f"/api/v1/datasets/{dataset['id']}/validate", headers=hr_headers
    ).json()
    assert any("single value" in w for w in report["warnings"])


def test_duplicate_rows_counted(client, hr_headers):
    content = CSV + "38,Finance,6800,9,No,No\n"
    body = _upload(client, hr_headers, content=content).json()
    assert body["duplicate_row_count"] == 1


def test_employee_cannot_upload_datasets(client, employee_headers):
    resp = _upload(client, employee_headers)
    assert resp.status_code == 403


def test_manager_cannot_upload_datasets(client, manager_headers):
    resp = _upload(client, manager_headers)
    assert resp.status_code == 403
