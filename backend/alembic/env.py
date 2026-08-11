"""Alembic environment configuration.

We use async SQLAlchemy via psycopg (v3) — the same driver used at
runtime. The connection URL comes from ``DATABASE_URL`` so dev / staging
/ prod share the same migration code.

The ``target_metadata`` is wired to ``app.models.Base.metadata`` so
``alembic revision --autogenerate`` can diff against the live schema.
"""

from __future__ import annotations

import contextlib
import sys
import warnings
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# On Windows, psycopg refuses to run inside the default ProactorEventLoop
# ("Psycopg cannot use the 'ProactorEventLoop' to run in async mode").
# Force the selector loop before any async engine is created. The
# selector-loop policy is deprecated on Python 3.14+ but still works;
# silence the warning locally.
if sys.platform == "win32":
    import asyncio  # noqa: E402

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with contextlib.suppress(AttributeError):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined,deprecated]  # noqa: E501  # type: ignore[attr-defined]

# Ensure ``app`` is importable when alembic is invoked from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models import Base  # noqa: E402  -- registers all ORM tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL with the runtime one — never trust the alembic.ini default.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare types so PG-only types (CITEXT, INET, JSONB) diff correctly.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
