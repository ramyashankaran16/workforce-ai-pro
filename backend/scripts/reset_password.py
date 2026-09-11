"""
Set a user's password directly, bypassing the API.

    python -m scripts.reset_password --email ramya@aiworkforce.ai --password "Ramya@123"

Also clears any lockout and reactivates the account.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password, verify_password  # noqa: E402
from app.models.enums import UserStatus  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a user's password")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--force-change",
        action="store_true",
        help="require a password change at next sign-in",
    )
    args = parser.parse_args()

    email = args.email.lower().strip()
    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            print(f"[FAIL] No user with email '{email}'.")
            return 1

        user.hashed_password = hash_password(args.password)
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_deleted = False
        user.must_change_password = args.force_change
        db.commit()
        db.refresh(user)

        assert verify_password(args.password, user.hashed_password)
        print(f"[OK] Password set for {email} (role: {user.role_name}).")
        print(f'\nLog in with:\n  {{"email": "{email}", "password": "{args.password}"}}')
        return 0
    except Exception as exc:
        db.rollback()
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
