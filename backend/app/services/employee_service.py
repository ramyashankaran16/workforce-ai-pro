"""Employee CRUD, code generation, history tracking and org-tree traversal."""

import csv
import io
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
    PermissionDeniedError,
)
from app.models.department import Department, Designation
from app.models.employee import Employee, EmployeeHistory
from app.models.enums import EmployeeEventType, EmployeeStatus, UserStatus
from app.models.user import User
from app.services import auth_service
from app.utils.code_generator import generate_employee_code

# Changes worth writing to EmployeeHistory, and the event they map to.
TRACKED_FIELDS: Dict[str, EmployeeEventType] = {
    "department_id": EmployeeEventType.TRANSFER,
    "designation_id": EmployeeEventType.PROMOTION,
    "manager_id": EmployeeEventType.MANAGER_CHANGE,
    "current_salary": EmployeeEventType.SALARY_REVISION,
    "status": EmployeeEventType.STATUS_CHANGE,
    "employment_type": EmployeeEventType.ROLE_CHANGE,
}


# ------------------------------------------------------------------ lookups
def get_employee(db: Session, employee_id: int) -> Employee:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.is_deleted:
        raise NotFoundError("Employee not found.")
    return emp


def get_by_user(db: Session, user_id: int) -> Optional[Employee]:
    return db.execute(
        select(Employee).where(
            Employee.user_id == user_id, Employee.is_deleted.is_(False)
        )
    ).scalar_one_or_none()


def reportee_count(db: Session, employee_id: int) -> int:
    return db.execute(
        select(func.count(Employee.id)).where(
            Employee.manager_id == employee_id, Employee.is_deleted.is_(False)
        )
    ).scalar() or 0


# ------------------------------------------------------------------- scoping
def scope_query(db: Session, stmt, current_user: User):
    """
    Narrow a select to what the caller may see.

    admin/hr  -> everyone
    manager   -> self plus direct reportees
    employee  -> self only

    This is the row-level half of RBAC. The permission check decides whether
    the endpoint can be called at all; this decides which rows come back.
    """
    role = (current_user.role_name or "").lower()
    if role in {"admin", "hr"}:
        return stmt

    profile = get_by_user(db, current_user.id)
    if profile is None:
        # No employee record: can see nothing rather than everything.
        return stmt.where(Employee.id == -1)

    if role == "manager":
        return stmt.where(
            or_(Employee.id == profile.id, Employee.manager_id == profile.id)
        )
    return stmt.where(Employee.id == profile.id)


def assert_can_access(db: Session, current_user: User, employee: Employee) -> None:
    role = (current_user.role_name or "").lower()
    if role in {"admin", "hr"}:
        return
    profile = get_by_user(db, current_user.id)
    if profile is None:
        raise PermissionDeniedError("No employee profile is linked to this account.")
    if employee.id == profile.id:
        return
    if role == "manager" and employee.manager_id == profile.id:
        return
    raise PermissionDeniedError("You do not have access to this employee record.")


# ------------------------------------------------------------------- history
def record_history(
    db: Session,
    employee_id: int,
    event_type: EmployeeEventType,
    effective_date: Optional[date] = None,
    field_name: Optional[str] = None,
    old_value=None,
    new_value=None,
    remarks: Optional[str] = None,
    changed_by_id: Optional[int] = None,
) -> None:
    db.add(
        EmployeeHistory(
            employee_id=employee_id,
            event_type=event_type,
            effective_date=effective_date or date.today(),
            field_name=field_name,
            old_value=None if old_value is None else str(old_value)[:255],
            new_value=None if new_value is None else str(new_value)[:255],
            remarks=remarks,
            changed_by_id=changed_by_id,
        )
    )


# -------------------------------------------------------------------- create
def create_employee(
    db: Session, data: dict, actor: Optional[User] = None
) -> Tuple[Employee, bool, Optional[str]]:
    """Create an employee, optionally with a linked login account."""
    create_account = data.pop("create_user_account", False)
    user_role = data.pop("user_role", "employee")
    user_password = data.pop("user_password", None)

    work_email = data["work_email"].lower().strip()
    data["work_email"] = work_email

    existing = db.execute(
        select(Employee).where(
            Employee.work_email == work_email, Employee.is_deleted.is_(False)
        )
    ).scalar_one_or_none()
    if existing:
        raise DuplicateError(f"An employee with {work_email} already exists.")

    code = (data.get("employee_code") or "").strip().upper()
    if code:
        clash = db.execute(
            select(Employee).where(Employee.employee_code == code)
        ).scalar_one_or_none()
        if clash:
            raise DuplicateError(f"Employee code '{code}' is already in use.")
    else:
        code = generate_employee_code(db)
    data["employee_code"] = code

    _validate_references(db, data)

    employee = Employee(**data)
    db.add(employee)
    db.flush()  # assign the id before writing history

    record_history(
        db,
        employee.id,
        EmployeeEventType.JOINED,
        effective_date=employee.date_of_joining,
        remarks=f"Joined as {employee.employment_type.value}",
        changed_by_id=actor.id if actor else None,
    )

    user_created = False
    temp_password = None
    if create_account:
        user, temp_password = auth_service.create_user(
            db,
            email=work_email,
            full_name=employee.full_name,
            role_name=user_role,
            password=user_password,
            phone=employee.phone,
        )
        employee.user_id = user.id
        user_created = True

    db.commit()
    db.refresh(employee)
    return employee, user_created, temp_password


# -------------------------------------------------------------------- update
def update_employee(
    db: Session, employee_id: int, data: dict, actor: Optional[User] = None
) -> Employee:
    employee = get_employee(db, employee_id)

    if "manager_id" in data and data["manager_id"] is not None:
        _validate_manager(db, employee_id, data["manager_id"])
    if "work_email" in data and data["work_email"]:
        data["work_email"] = data["work_email"].lower().strip()
        clash = db.execute(
            select(Employee).where(
                Employee.work_email == data["work_email"],
                Employee.id != employee_id,
                Employee.is_deleted.is_(False),
            )
        ).scalar_one_or_none()
        if clash:
            raise DuplicateError("That work email belongs to another employee.")

    _validate_references(db, data)

    for field, value in data.items():
        old = getattr(employee, field, None)
        if old == value:
            continue

        if field in TRACKED_FIELDS:
            record_history(
                db,
                employee.id,
                TRACKED_FIELDS[field],
                field_name=field,
                old_value=_label(old),
                new_value=_label(value),
                changed_by_id=actor.id if actor else None,
            )
            if field == "current_salary" and old and value:
                try:
                    employee.last_hike_percent = round(
                        ((float(value) - float(old)) / float(old)) * 100, 2
                    )
                    employee.last_hike_date = date.today()
                except ZeroDivisionError:
                    pass

        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return employee


# ---------------------------------------------------------------------- exit
def record_exit(
    db: Session, employee_id: int, data: dict, actor: Optional[User] = None
) -> Employee:
    employee = get_employee(db, employee_id)
    if employee.date_of_exit:
        raise BusinessRuleError("An exit has already been recorded for this employee.")
    if data["date_of_exit"] < employee.date_of_joining:
        raise BusinessRuleError("Exit date cannot precede the joining date.")

    reportees = reportee_count(db, employee_id)
    if reportees:
        raise BusinessRuleError(
            f"{reportees} employee(s) still report to this person. "
            "Reassign them before recording an exit."
        )

    deactivate = data.pop("deactivate_user", True)
    employee.date_of_exit = data["date_of_exit"]
    employee.status = data["status"]
    employee.exit_reason = data["exit_reason"]

    record_history(
        db,
        employee.id,
        EmployeeEventType.EXIT,
        effective_date=data["date_of_exit"],
        field_name="status",
        new_value=data["status"].value,
        remarks=data["exit_reason"],
        changed_by_id=actor.id if actor else None,
    )

    if deactivate and employee.user_id:
        user = db.get(User, employee.user_id)
        if user:
            user.status = UserStatus.INACTIVE
            auth_service.revoke_all_tokens(db, user.id)

    db.commit()
    db.refresh(employee)
    return employee


def soft_delete(db: Session, employee_id: int) -> None:
    employee = get_employee(db, employee_id)
    if reportee_count(db, employee_id):
        raise BusinessRuleError(
            "Reassign this person's reportees before deleting the record."
        )
    employee.is_deleted = True
    if employee.user_id:
        user = db.get(User, employee.user_id)
        if user:
            user.status = UserStatus.INACTIVE
    db.commit()


# ------------------------------------------------------------------ org tree
def org_tree(db: Session, root_id: Optional[int] = None, max_depth: int = 6) -> List[dict]:
    """
    Reporting tree. Loads every active employee once and assembles in memory --
    a recursive query per node would be N+1.
    """
    employees = (
        db.execute(
            select(Employee)
            .options(
                selectinload(Employee.designation), selectinload(Employee.department)
            )
            .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
        )
        .scalars()
        .all()
    )

    by_manager: Dict[Optional[int], List[Employee]] = {}
    for emp in employees:
        by_manager.setdefault(emp.manager_id, []).append(emp)

    def node(emp: Employee, depth: int) -> dict:
        return {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "full_name": emp.full_name,
            "designation_title": emp.designation.title if emp.designation else None,
            "department_name": emp.department.name if emp.department else None,
            "reportees": (
                [node(child, depth + 1) for child in by_manager.get(emp.id, [])]
                if depth < max_depth
                else []
            ),
        }

    if root_id is not None:
        root = get_employee(db, root_id)
        return [node(root, 0)]
    return [node(emp, 0) for emp in by_manager.get(None, [])]


# --------------------------------------------------------------- bulk import
IMPORT_COLUMNS = [
    "first_name", "last_name", "work_email", "phone", "date_of_joining",
    "department_code", "designation_code", "manager_code", "employment_type",
    "work_mode", "current_salary",
]


def import_csv(db: Session, content: bytes, actor: Optional[User] = None) -> dict:
    """Import employees from CSV. Each row is independent -- one bad row does
    not abort the rest."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    created = 0
    skipped = 0
    failures: List[dict] = []

    dept_codes = {
        d.code: d.id
        for d in db.execute(select(Department).where(Department.is_deleted.is_(False)))
        .scalars()
        .all()
    }
    desig_codes = {
        d.code: d.id
        for d in db.execute(select(Designation).where(Designation.is_deleted.is_(False)))
        .scalars()
        .all()
        if d.code
    }

    for index, row in enumerate(reader, start=2):  # row 1 is the header
        email = (row.get("work_email") or "").strip().lower()
        try:
            if not email or not (row.get("first_name") or "").strip():
                raise ValueError("first_name and work_email are required.")

            exists = db.execute(
                select(Employee).where(Employee.work_email == email)
            ).scalar_one_or_none()
            if exists:
                skipped += 1
                continue

            manager_code = (row.get("manager_code") or "").strip().upper()
            manager_id = None
            if manager_code:
                manager = db.execute(
                    select(Employee).where(Employee.employee_code == manager_code)
                ).scalar_one_or_none()
                if manager is None:
                    raise ValueError(f"Unknown manager_code '{manager_code}'.")
                manager_id = manager.id

            payload = {
                "first_name": row["first_name"].strip(),
                "last_name": (row.get("last_name") or "").strip() or None,
                "work_email": email,
                "phone": (row.get("phone") or "").strip() or None,
                "date_of_joining": date.fromisoformat(row["date_of_joining"].strip()),
                "department_id": dept_codes.get(
                    (row.get("department_code") or "").strip().upper()
                ),
                "designation_id": desig_codes.get(
                    (row.get("designation_code") or "").strip().upper()
                ),
                "manager_id": manager_id,
                "employee_code": generate_employee_code(db),
            }
            if (row.get("current_salary") or "").strip():
                payload["current_salary"] = float(row["current_salary"])

            employee = Employee(**payload)
            db.add(employee)
            db.flush()
            record_history(
                db,
                employee.id,
                EmployeeEventType.JOINED,
                effective_date=employee.date_of_joining,
                remarks="Bulk import",
                changed_by_id=actor.id if actor else None,
            )
            db.commit()
            created += 1
        except Exception as exc:
            db.rollback()
            failures.append(
                {"row_number": index, "work_email": email or None, "error": str(exc)[:200]}
            )

    return {
        "total_rows": created + skipped + len(failures),
        "created": created,
        "skipped": skipped,
        "failures": failures,
    }


# ------------------------------------------------------------------ helpers
def _validate_manager(db: Session, employee_id: int, manager_id: int) -> None:
    if manager_id == employee_id:
        raise BusinessRuleError("An employee cannot be their own manager.")

    manager = db.get(Employee, manager_id)
    if manager is None or manager.is_deleted:
        raise NotFoundError(f"Manager {manager_id} not found.")

    # walk up the chain looking for ourselves
    seen = set()
    current = manager.manager_id
    while current is not None:
        if current == employee_id:
            raise BusinessRuleError(
                "That manager reports to this employee -- it would create a cycle."
            )
        if current in seen:
            break
        seen.add(current)
        current = db.execute(
            select(Employee.manager_id).where(Employee.id == current)
        ).scalar_one_or_none()


def _validate_references(db: Session, data: dict) -> None:
    if data.get("department_id"):
        dept = db.get(Department, data["department_id"])
        if dept is None or dept.is_deleted:
            raise NotFoundError(f"Department {data['department_id']} not found.")
    if data.get("designation_id"):
        desig = db.get(Designation, data["designation_id"])
        if desig is None or desig.is_deleted:
            raise NotFoundError(f"Designation {data['designation_id']} not found.")


def _label(value):
    return value.value if hasattr(value, "value") else value


def build_detail(db: Session, employee: Employee) -> dict:
    """EmployeeDetail payload with resolved labels."""
    payload = {
        c.name: getattr(employee, c.name) for c in employee.__table__.columns
    }
    payload.update(
        {
            "full_name": employee.full_name,
            "tenure_months": employee.tenure_months,
            "department_name": employee.department.name if employee.department else None,
            "designation_title": (
                employee.designation.title if employee.designation else None
            ),
            "manager_name": employee.manager.full_name if employee.manager else None,
            "reportee_count": reportee_count(db, employee.id),
        }
    )
    return payload
