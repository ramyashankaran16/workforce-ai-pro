"""
Alembic environment.

The database URL comes from app settings rather than alembic.ini, so there is
one source of truth. Note that we build the Engine directly instead of calling
config.set_main_option("sqlalchemy.url", ...) -- Alembic's config is a
ConfigParser, which treats '%' as an interpolation character and would mangle
any password containing one.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401,E402  -- registers every model
from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _fail_fast_if_no_credentials() -> None:
    if not settings.DB_PASSWORD:
        raise SystemExit(
            "\n[FAIL] DB_PASSWORD is empty.\n"
            f"       Settings source : {settings.describe_source()}\n"
            f"       Working dir     : {Path.cwd()}\n"
            "       Set DB_PASSWORD in backend/.env, then retry.\n"
            "       Diagnose with: python -m scripts.check_db\n"
        )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=settings.DATABASE_URL.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    _fail_fast_if_no_credentials()

    # URL object passed straight to create_engine - no string round-trip,
    # so special characters in the password are never re-parsed.
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
