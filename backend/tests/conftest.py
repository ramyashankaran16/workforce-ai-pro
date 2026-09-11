"""Test fixtures: in-memory SQLite database and role-specific clients."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: F401,E402  -- registers every model
from app.core.database import Base, get_db  # noqa: E402
from app.core.permissions import (  # noqa: E402
    PERMISSION_CATALOGUE,
    ROLE_DEFINITIONS,
    ROLE_PERMISSIONS,
)
from app.core.security import hash_password  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.enums import UserStatus  # noqa: E402
from app.models.role import Permission, Role  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_PASSWORD = "TestPass123"


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()

    # roles + permissions
    perms = {}
    for code, name, module in PERMISSION_CATALOGUE:
        p = Permission(code=code, name=name, module=module)
        session.add(p)
        perms[code] = p
    session.flush()

    for name, (display, level, description) in ROLE_DEFINITIONS.items():
        role = Role(
            name=name,
            display_name=display,
            description=description,
            hierarchy_level=level,
            is_system_role=True,
        )
        role.permissions = [perms[c] for c in ROLE_PERMISSIONS.get(name, []) if c in perms]
        session.add(role)
    session.commit()

    # one user per role
    for role_name in ROLE_DEFINITIONS:
        role = session.execute(
            select(Role).where(Role.name == role_name)
        ).scalar_one()
        session.add(
            User(
                email=f"{role_name}@test.com",
                full_name=f"Test {role_name.title()}",
                hashed_password=hash_password(TEST_PASSWORD),
                role_id=role.id,
                status=UserStatus.ACTIVE,
            )
        )
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


def _token_for(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(client):
    return {"Authorization": f"Bearer {_token_for(client, 'admin@test.com')}"}


@pytest.fixture
def hr_headers(client):
    return {"Authorization": f"Bearer {_token_for(client, 'hr@test.com')}"}


@pytest.fixture
def manager_headers(client):
    return {"Authorization": f"Bearer {_token_for(client, 'manager@test.com')}"}


@pytest.fixture
def employee_headers(client):
    return {"Authorization": f"Bearer {_token_for(client, 'employee@test.com')}"}

@pytest.fixture
def org(db_session):
    """
    A small organisation wired to the role fixtures:

        manager@test.com  -> Meera Manager   (EMP0002)
        employee@test.com -> Eshan Employee  (EMP0003, reports to Meera)
                             Nita NoAccess   (EMP0004, reports to nobody)

    Returns a dict of ids so tests can assert on specific rows.
    """
    from datetime import date

    from app.models.department import Department, Designation
    from app.models.employee import Employee

    eng = Department(code="ENG", name="Engineering")
    hr_dept = Department(code="HR", name="Human Resources")
    db_session.add_all([eng, hr_dept])
    db_session.flush()

    senior = Designation(code="SE2", title="Senior Software Engineer", level=2)
    lead = Designation(code="TL", title="Team Lead", level=3)
    db_session.add_all([senior, lead])
    db_session.flush()

    hr_user = db_session.execute(
        select(User).where(User.email == "hr@test.com")
    ).scalar_one()
    manager_user = db_session.execute(
        select(User).where(User.email == "manager@test.com")
    ).scalar_one()
    employee_user = db_session.execute(
        select(User).where(User.email == "employee@test.com")
    ).scalar_one()

    hr_emp = Employee(
        employee_code="EMP0001", first_name="Hana", last_name="HR",
        work_email="hr@test.com", date_of_joining=date(2020, 1, 15),
        department_id=hr_dept.id, user_id=hr_user.id,
    )
    manager = Employee(
        employee_code="EMP0002", first_name="Meera", last_name="Manager",
        work_email="manager@test.com", date_of_joining=date(2021, 3, 1),
        department_id=eng.id, designation_id=lead.id, user_id=manager_user.id,
    )
    db_session.add_all([hr_emp, manager])
    db_session.flush()

    reportee = Employee(
        employee_code="EMP0003", first_name="Eshan", last_name="Employee",
        work_email="employee@test.com", date_of_joining=date(2022, 6, 10),
        department_id=eng.id, designation_id=senior.id,
        manager_id=manager.id, user_id=employee_user.id,
        current_salary=600000,
    )
    outsider = Employee(
        employee_code="EMP0004", first_name="Nita", last_name="NoAccess",
        work_email="nita@test.com", date_of_joining=date(2023, 2, 1),
        department_id=hr_dept.id,
    )
    db_session.add_all([reportee, outsider])
    db_session.commit()

    return {
        "eng_id": eng.id,
        "hr_dept_id": hr_dept.id,
        "senior_id": senior.id,
        "lead_id": lead.id,
        "hr_emp_id": hr_emp.id,
        "manager_id": manager.id,
        "reportee_id": reportee.id,
        "outsider_id": outsider.id,
    }
