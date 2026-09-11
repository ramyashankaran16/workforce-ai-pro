"""
Seed roles, permissions, the default admin and baseline master data.

    python -m scripts.seed_data
    python -m scripts.seed_data --reset-permissions

Safe to run repeatedly: existing rows are updated, not duplicated.
"""

import argparse
import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.permissions import (  # noqa: E402
    PERMISSION_CATALOGUE,
    ROLE_DEFINITIONS,
    ROLE_PERMISSIONS,
)
from app.core.security import hash_password  # noqa: E402
from app.models.attendance import Shift  # noqa: E402
from app.models.department import Department, Designation  # noqa: E402
from app.models.document import DocumentCategory  # noqa: E402
from app.models.enums import ShiftType, UserStatus  # noqa: E402
from app.models.leave import LeaveType  # noqa: E402
from app.models.role import Permission, Role  # noqa: E402
from app.models.user import User  # noqa: E402


def seed_permissions(db: Session) -> dict:
    existing = {p.code: p for p in db.execute(select(Permission)).scalars().all()}
    created = 0
    for code, name, module in PERMISSION_CATALOGUE:
        perm = existing.get(code)
        if perm is None:
            perm = Permission(code=code, name=name, module=module)
            db.add(perm)
            existing[code] = perm
            created += 1
        else:
            perm.name = name
            perm.module = module
    db.commit()
    print(f"  permissions : {created} created, {len(existing) - created} updated")
    return {p.code: p for p in db.execute(select(Permission)).scalars().all()}


def seed_roles(db: Session, perms: dict) -> dict:
    created = 0
    for name, (display, level, description) in ROLE_DEFINITIONS.items():
        role = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
        if role is None:
            role = Role(
                name=name,
                display_name=display,
                description=description,
                hierarchy_level=level,
                is_system_role=True,
            )
            db.add(role)
            created += 1
        else:
            role.display_name = display
            role.description = description
            role.hierarchy_level = level

        codes = ROLE_PERMISSIONS.get(name, [])
        role.permissions = [perms[c] for c in codes if c in perms]
    db.commit()

    roles = {r.name: r for r in db.execute(select(Role)).scalars().all()}
    print(f"  roles       : {created} created, {len(ROLE_DEFINITIONS) - created} updated")
    for name, role in sorted(roles.items(), key=lambda kv: kv[1].hierarchy_level):
        print(f"                {name:<9} level {role.hierarchy_level}  "
              f"{len(role.permissions):>2} permissions")
    return roles


def seed_admin(db: Session, roles: dict) -> None:
    """
    Ensure an admin account exists for DEFAULT_ADMIN_EMAIL.

    Checked by email AND by username, because a previous seed with a different
    email may already own the username.
    """
    email = settings.DEFAULT_ADMIN_EMAIL.lower().strip()

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        print(f"  admin       : already exists ({email})")
        return

    # derive a username from the email local part, then de-duplicate
    base = email.split("@")[0][:70] or "admin"
    username = base
    suffix = 1
    while db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        suffix += 1
        username = f"{base}{suffix}"

    db.add(
        User(
            email=email,
            username=username,
            full_name="System Administrator",
            hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            role_id=roles["admin"].id,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
            must_change_password=True,
        )
    )
    db.commit()
    print(f"  admin       : created {email} (username: {username})")
    print(f"                password {settings.DEFAULT_ADMIN_PASSWORD} "
          "- must be changed at first sign-in")

    others = (
        db.execute(
            select(User)
            .where(User.role_id == roles["admin"].id, User.email != email)
        )
        .scalars()
        .all()
    )
    if others:
        print(f"                note: {len(others)} other admin account(s) exist: "
              + ", ".join(u.email for u in others))


def seed_departments(db: Session) -> None:
    rows = [
        ("ENG", "Engineering", "Product development and platform engineering"),
        ("HR", "Human Resources", "People operations and talent management"),
        ("SALES", "Sales", "Revenue and client acquisition"),
        ("FIN", "Finance", "Accounting, payroll and compliance"),
        ("OPS", "Operations", "Delivery and internal operations"),
        ("MKT", "Marketing", "Brand, demand generation and communications"),
    ]
    created = 0
    for code, name, description in rows:
        if db.execute(select(Department).where(Department.code == code)).scalar_one_or_none():
            continue
        db.add(Department(code=code, name=name, description=description))
        created += 1
    db.commit()
    print(f"  departments : {created} created")


def seed_designations(db: Session) -> None:
    rows = [
        ("SE1", "Software Engineer", 1),
        ("SE2", "Senior Software Engineer", 2),
        ("TL", "Team Lead", 3),
        ("EM", "Engineering Manager", 4),
        ("HRE", "HR Executive", 1),
        ("HRM", "HR Manager", 3),
        ("SEX", "Sales Executive", 1),
        ("SMG", "Sales Manager", 3),
        ("ACC", "Accountant", 1),
        ("DIR", "Director", 5),
    ]
    created = 0
    for code, title, level in rows:
        if db.execute(select(Designation).where(Designation.code == code)).scalar_one_or_none():
            continue
        db.add(Designation(code=code, title=title, level=level))
        created += 1
    db.commit()
    print(f"  designations: {created} created")


def seed_leave_types(db: Session) -> None:
    rows = [
        ("CL", "Casual Leave", 12.0, True, False, "#3b82f6"),
        ("SL", "Sick Leave", 12.0, True, False, "#ef4444"),
        ("EL", "Earned Leave", 15.0, True, True, "#22c55e"),
        ("LOP", "Loss of Pay", 0.0, False, False, "#6b7280"),
        ("ML", "Maternity Leave", 182.0, True, False, "#ec4899"),
        ("PL", "Paternity Leave", 15.0, True, False, "#8b5cf6"),
        ("CO", "Compensatory Off", 0.0, True, False, "#f59e0b"),
    ]
    created = 0
    for code, name, quota, is_paid, carry, colour in rows:
        if db.execute(select(LeaveType).where(LeaveType.code == code)).scalar_one_or_none():
            continue
        db.add(
            LeaveType(
                code=code,
                name=name,
                annual_quota=quota,
                is_paid=is_paid,
                is_carry_forward=carry,
                max_carry_forward=10.0 if carry else 0.0,
                requires_document=(code == "SL"),
                color_code=colour,
            )
        )
        created += 1
    db.commit()
    print(f"  leave types : {created} created")


def seed_shifts(db: Session) -> None:
    rows = [
        ("GEN", "General Shift", ShiftType.GENERAL, time(9, 0), time(18, 0), False),
        ("MOR", "Morning Shift", ShiftType.MORNING, time(6, 0), time(14, 0), False),
        ("EVE", "Evening Shift", ShiftType.EVENING, time(14, 0), time(22, 0), False),
        ("NGT", "Night Shift", ShiftType.NIGHT, time(22, 0), time(6, 0), True),
    ]
    created = 0
    for code, name, shift_type, start, end, is_night in rows:
        if db.execute(select(Shift).where(Shift.code == code)).scalar_one_or_none():
            continue
        db.add(
            Shift(
                code=code,
                name=name,
                shift_type=shift_type,
                start_time=start,
                end_time=end,
                is_night_shift=is_night,
                working_hours=8.0,
            )
        )
        created += 1
    db.commit()
    print(f"  shifts      : {created} created")


def seed_document_categories(db: Session) -> None:
    rows = [
        ("IDPROOF", "Identity Proof", True, True),
        ("ADDRESS", "Address Proof", True, False),
        ("EDU", "Educational Certificate", True, False),
        ("EXP", "Experience Letter", False, False),
        ("OFFER", "Offer Letter", False, False),
        ("CONTRACT", "Employment Contract", True, True),
        ("PAYSLIP", "Previous Payslip", False, False),
        ("MEDICAL", "Medical Record", False, True),
    ]
    created = 0
    for code, name, mandatory, expiry in rows:
        if db.execute(
            select(DocumentCategory).where(DocumentCategory.code == code)
        ).scalar_one_or_none():
            continue
        db.add(
            DocumentCategory(
                code=code, name=name, is_mandatory=mandatory, requires_expiry=expiry
            )
        )
        created += 1
    db.commit()
    print(f"  doc types   : {created} created")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed baseline data")
    parser.add_argument(
        "--reset-permissions",
        action="store_true",
        help="rebuild role-permission links from the catalogue",
    )
    args = parser.parse_args()

    print(f"Seeding {settings.DB_NAME} @ {settings.DB_HOST}:{settings.DB_PORT}\n")
    db = SessionLocal()
    try:
        perms = seed_permissions(db)
        roles = seed_roles(db, perms)
        seed_admin(db, roles)
        seed_departments(db)
        seed_designations(db)
        seed_leave_types(db)
        seed_shifts(db)
        seed_document_categories(db)
        print("\n[OK] Seeding complete.")
        print(f"\nSign in at POST {settings.API_V1_PREFIX}/auth/login")
        print(f'  {{"email": "{settings.DEFAULT_ADMIN_EMAIL}", '
              f'"password": "{settings.DEFAULT_ADMIN_PASSWORD}"}}')
        return 0
    except Exception as exc:
        db.rollback()
        print(f"\n[FAIL] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
