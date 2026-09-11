"""
Diagnostic: show exactly which settings are loaded and test the connection.

    python -m scripts.check_db
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402

print(f"settings src: {settings.describe_source()}")
print(f"working dir : {Path.cwd()}")
print(f"DB_HOST     : {settings.DB_HOST}")
print(f"DB_PORT     : {settings.DB_PORT}")
print(f"DB_USER     : {settings.DB_USER}")
print(f"DB_NAME     : {settings.DB_NAME}")
print(f"DB_PASSWORD : {'<empty>' if not settings.DB_PASSWORD else repr(settings.DB_PASSWORD)}")
print(f"  length    : {len(settings.DB_PASSWORD)}")

try:
    with create_engine(settings.SERVER_URL).connect() as conn:
        print("\n[OK] Credentials accepted by the server.")
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": settings.DB_NAME},
        ).scalar()
        if exists:
            print(f"[OK] Database '{settings.DB_NAME}' exists.")
        else:
            print(f"[--] Database '{settings.DB_NAME}' does not exist yet.")
            print("     Run: python -m scripts.create_tables --create-db")
except Exception as exc:
    print(f"\n[FAIL] {type(exc).__name__}: {exc}")
