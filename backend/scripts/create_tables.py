"""
Create every table in PostgreSQL from the ORM metadata.

Usage (from the backend folder, venv active):
    python -m scripts.create_tables
    python -m scripts.create_tables --drop        # drop all tables first
    python -m scripts.create_tables --create-db   # create the database if missing

Once the schema is stable, switch to Alembic migrations instead.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

import app.models  # noqa: F401,E402  -- registers every model
from app.core.config import settings  # noqa: E402
from app.core.database import Base, engine  # noqa: E402


def create_database_if_missing() -> bool:
    """Connect to the maintenance 'postgres' database and CREATE DATABASE."""
    try:
        # AUTOCOMMIT is required: CREATE DATABASE cannot run inside a transaction
        server = create_engine(settings.SERVER_URL, isolation_level="AUTOCOMMIT")
        with server.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": settings.DB_NAME},
            ).scalar()
            if exists:
                print(f"[OK] Database '{settings.DB_NAME}' already exists.")
            else:
                conn.execute(text(f'CREATE DATABASE "{settings.DB_NAME}"'))
                print(f"[OK] Created database '{settings.DB_NAME}'.")
        return True
    except Exception as exc:
        print(f"[FAIL] Could not create the database: {exc}")
        return False


def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        print(f"Server   : {str(version).split(',')[0]}")
        return True
    except Exception as exc:
        message = str(exc)
        print("[FAIL] Cannot connect to PostgreSQL")
        print(f"       Host={settings.DB_HOST}:{settings.DB_PORT} "
              f"User={settings.DB_USER} DB={settings.DB_NAME}")

        if "password authentication failed" in message:
            print("\n       Cause: wrong username or password.")
            print("       Check DB_USER / DB_PASSWORD in your .env file.")
        elif "does not exist" in message and "database" in message:
            print("\n       Cause: the database does not exist yet.")
            print("       Run:  python -m scripts.create_tables --create-db")
        elif "could not connect" in message or "Connection refused" in message:
            print("\n       Cause: the PostgreSQL service is not running.")
            print("       Start it:  net start postgresql-x64-17")
            print("       (adjust the version number to match your install)")
        else:
            print(f"\n       {message}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Create WorkForce AI Pro tables")
    parser.add_argument("--drop", action="store_true", help="drop all tables first")
    parser.add_argument(
        "--create-db", action="store_true", help="create the database if it is missing"
    )
    args = parser.parse_args()

    print(f"Database : {settings.DB_NAME} @ {settings.DB_HOST}:{settings.DB_PORT}")

    if args.create_db and not create_database_if_missing():
        return 1

    if not check_connection():
        return 1

    if args.drop:
        confirm = input("This deletes ALL data. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 0
        print("Dropping tables...")
        Base.metadata.drop_all(bind=engine)

    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    tables = sorted(inspect(engine).get_table_names(schema=settings.DB_SCHEMA))
    print(f"\n[OK] {len(tables)} tables present in schema '{settings.DB_SCHEMA}':\n")
    for i, name in enumerate(tables, 1):
        print(f"  {i:2d}. {name}")

    settings.ensure_directories()
    print("\nRuntime directories ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
