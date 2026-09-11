"""Department and designation management, headcount rollups, cycle detection."""

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleError, DuplicateError, NotFoundError
from app.models.department import Department, Designation
from app.models.employee import Employee


# ------------------------------------------------------------------ lookups
def get_department(db: Session, department_id: int) -> Department:
    dept = db.get(Department, department_id)
    if dept is None or dept.is_deleted:
        raise NotFoundError("Department not found.")
    return dept


def get_designation(db: Session, designation_id: int) -> Designation:
    desig = db.get(Designation, designation_id)
    if desig is None or desig.is_deleted:
        raise NotFoundError("Designation not found.")
    return desig


def headcount_map(db: Session) -> Dict[int, int]:
    """department_id -> count of active, non-deleted employees."""
    rows = db.execute(
        select(Employee.department_id, func.count(Employee.id))
        .where(Employee.is_deleted.is_(False), Employee.date_of_exit.is_(None))
        .group_by(Employee.department_id)
    ).all()
    return {dept_id: count for dept_id, count in rows if dept_id is not None}


# ------------------------------------------------------------- cycle safety
def _would_create_cycle(db: Session, department_id: int, new_parent_id: int) -> bool:
    """Walk up from the proposed parent; if we meet ourselves, it's a cycle."""
    seen = set()
    current: Optional[int] = new_parent_id
    while current is not None:
        if current == department_id:
            return True
        if current in seen:  # pre-existing loop, stop rather than spin
            return True
        seen.add(current)
        parent = db.execute(
            select(Department.parent_id).where(Department.id == current)
        ).scalar_one_or_none()
        current = parent
    return False


# --------------------------------------------------------------- department
def create_department(db: Session, data: dict) -> Department:
    code = data["code"].upper().strip()
    existing = db.execute(
        select(Department).where(Department.code == code)
    ).scalar_one_or_none()
    if existing:
        raise DuplicateError(f"Department code '{code}' is already in use.")

    if data.get("parent_id"):
        get_department(db, data["parent_id"])
    if data.get("head_employee_id"):
        _require_employee(db, data["head_employee_id"])

    dept = Department(**{**data, "code": code})
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def update_department(db: Session, department_id: int, data: dict) -> Department:
    dept = get_department(db, department_id)

    if "parent_id" in data and data["parent_id"] is not None:
        if data["parent_id"] == department_id:
            raise BusinessRuleError("A department cannot be its own parent.")
        get_department(db, data["parent_id"])
        if _would_create_cycle(db, department_id, data["parent_id"]):
            raise BusinessRuleError(
                "That parent would create a cycle in the department hierarchy."
            )

    if data.get("head_employee_id"):
        _require_employee(db, data["head_employee_id"])

    for field, value in data.items():
        setattr(dept, field, value)

    db.commit()
    db.refresh(dept)
    return dept


def delete_department(db: Session, department_id: int) -> None:
    dept = get_department(db, department_id)

    staff = db.execute(
        select(func.count(Employee.id)).where(
            Employee.department_id == department_id,
            Employee.is_deleted.is_(False),
        )
    ).scalar()
    if staff:
        raise BusinessRuleError(
            f"{staff} employee(s) are still assigned to this department."
        )

    children = db.execute(
        select(func.count(Department.id)).where(
            Department.parent_id == department_id,
            Department.is_deleted.is_(False),
        )
    ).scalar()
    if children:
        raise BusinessRuleError(
            f"{children} sub-department(s) still report to this department."
        )

    dept.is_deleted = True
    dept.is_active = False
    db.commit()


def build_tree(db: Session) -> List[dict]:
    """Nested department tree with headcounts."""
    departments = (
        db.execute(
            select(Department)
            .where(Department.is_deleted.is_(False))
            .order_by(Department.name)
        )
        .scalars()
        .all()
    )
    counts = headcount_map(db)

    nodes = {
        d.id: {
            "id": d.id,
            "code": d.code,
            "name": d.name,
            "description": d.description,
            "location": d.location,
            "budget": float(d.budget) if d.budget is not None else None,
            "headcount_limit": d.headcount_limit,
            "parent_id": d.parent_id,
            "head_employee_id": d.head_employee_id,
            "is_active": d.is_active,
            "headcount": counts.get(d.id, 0),
            "children": [],
        }
        for d in departments
    }

    roots: List[dict] = []
    for node in nodes.values():
        parent = nodes.get(node["parent_id"]) if node["parent_id"] else None
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)
    return roots


# -------------------------------------------------------------- designation
def create_designation(db: Session, data: dict) -> Designation:
    code = (data.get("code") or "").upper().strip() or None
    if code:
        existing = db.execute(
            select(Designation).where(Designation.code == code)
        ).scalar_one_or_none()
        if existing:
            raise DuplicateError(f"Designation code '{code}' is already in use.")

    _validate_salary_band(data.get("min_salary"), data.get("max_salary"))

    if data.get("department_id"):
        get_department(db, data["department_id"])

    desig = Designation(**{**data, "code": code})
    db.add(desig)
    db.commit()
    db.refresh(desig)
    return desig


def update_designation(db: Session, designation_id: int, data: dict) -> Designation:
    desig = get_designation(db, designation_id)

    _validate_salary_band(
        data.get("min_salary", desig.min_salary),
        data.get("max_salary", desig.max_salary),
    )
    if data.get("department_id"):
        get_department(db, data["department_id"])

    for field, value in data.items():
        setattr(desig, field, value)

    db.commit()
    db.refresh(desig)
    return desig


def delete_designation(db: Session, designation_id: int) -> None:
    desig = get_designation(db, designation_id)
    in_use = db.execute(
        select(func.count(Employee.id)).where(
            Employee.designation_id == designation_id,
            Employee.is_deleted.is_(False),
        )
    ).scalar()
    if in_use:
        raise BusinessRuleError(
            f"{in_use} employee(s) still hold this designation."
        )
    desig.is_deleted = True
    desig.is_active = False
    db.commit()


# ------------------------------------------------------------------ helpers
def _require_employee(db: Session, employee_id: int) -> Employee:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.is_deleted:
        raise NotFoundError(f"Employee {employee_id} not found.")
    return emp


def _validate_salary_band(minimum, maximum) -> None:
    if minimum is not None and maximum is not None and float(minimum) > float(maximum):
        raise BusinessRuleError("min_salary cannot exceed max_salary.")
