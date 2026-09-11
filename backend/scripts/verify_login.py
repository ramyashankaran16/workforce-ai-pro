"""
Diagnose a failing login by checking the database directly.

    python -m scripts.verify_login
    python -m scripts.verify_login --email ramya@aiworkforce.ai --password "Ramya@123"

Reports exactly which check fails: missing user, wrong password, inactive
status or an active lockout.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.models.enums import UserStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.date_utils import utcnow  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose a failing login")
    parser.add_argument("--email", default=settings.DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--password", default=settings.DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    email = args.email.lower().strip()
    print(f"Checking : {email}")
    print(f"Password : {args.password!r} (length {len(args.password)})")
    print(f"Database : {settings.DB_NAME} @ {settings.DB_HOST}:{settings.DB_PORT}\n")

    db = SessionLocal()
    try:
        all_users = db.execute(select(User)).scalars().all()
        print(f"Users in database: {len(all_users)}")
        for u in all_users:
            flag = " <-- target" if u.email == email else ""
            print(f"  id={u.id:<3} {u.email:<32} role={u.role_name:<9} "
                  f"status={u.status.value}{flag}")
        print()

        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if user is None:
            print(f"[FAIL] No user with email '{email}'.")
            print("       The seed did not create it. Check DEFAULT_ADMIN_EMAIL in .env,")
            print("       then run: python -m scripts.seed_data")
            return 1
        print(f"[OK]   User found (id={user.id}).")

        if user.is_deleted:
            print("[FAIL] User is soft-deleted (is_deleted = true).")
            return 1
        print("[OK]   Not deleted.")

        if user.status != UserStatus.ACTIVE:
            print(f"[FAIL] Status is '{user.status.value}', not 'active'.")
            print(f"       Fix: POST /api/v1/users/{user.id}/activate")
            return 1
        print("[OK]   Status is active.")

        if user.locked_until and user.locked_until > utcnow():
            mins = int((user.locked_until - utcnow()).total_seconds() // 60) + 1
            print(f"[FAIL] Locked for another {mins} minute(s) "
                  f"(until {user.locked_until}).")
            print("       That returns 423, not 401.")
            return 1
        print(f"[OK]   Not locked (failed attempts: {user.failed_login_attempts}).")

        if verify_password(args.password, user.hashed_password):
            print("[OK]   Password matches.\n")
            print("Login should succeed. Send exactly:")
            print(f'  {{"email": "{email}", "password": "{args.password}"}}')
            return 0

        print("[FAIL] Password does not match the stored hash.")
        print(f"       Stored hash starts: {user.hashed_password[:20]}...")
        print("\n       Reset it with:")
        print(f'       python -m scripts.reset_password --email {email} '
              f'--password "{args.password}"')
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
