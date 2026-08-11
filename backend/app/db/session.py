"""Async SQLAlchemy engine + session factory.

A single ``engine`` is created at import time from ``settings.database_url``.
The ``SessionLocal`` factory yields ``AsyncSession`` instances that request
handlers use via the ``get_db`` dependency.

We use SQLAlchemy 2.x's async engine with the psycopg v3 driver
(``postgresql+psycopg://``). The driver's connection pool is configured via
SQLAlchemy's ``pool_size`` and ``max_overflow`` derived from
``settings.database_pool_size``.

On Windows psycopg refuses to run on the default ``ProactorEventLoop``.
``app/__main__.py`` patches uvicorn's loop factory so the FastAPI worker
uses ``SelectorEventLoop``; tests that don't go through uvicorn set the
asyncio event-loop policy via ``conftest.py``. Both paths require the
selector loop to make a psycopg connection.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Belt-and-suspenders for ``app.db.session`` imported by contexts that
# haven't already patched uvicorn (e.g. unit tests that call
# ``engine.connect()`` directly from a worker thread, ad-hoc REPL
# sessions, or scripts that import ``app.db.session`` for migrations).
# The deprecation in Python 3.16+ will be replaced with the
# ``asyncio.EventLoopPolicy`` builder API; for now the policy setter is
# the supported way to influence which loop ``asyncio.new_event_loop()``
# creates.
if sys.platform == "win32":
    import asyncio  # noqa: E402
    import contextlib  # noqa: E402
    import warnings  # noqa: E402

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with contextlib.suppress(AttributeError):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # noqa: E501

# ``future=True`` (default in 2.x) + ``pool_pre_ping=True`` so a stale
# connection left idle in the pool is re-validated before use. Helpful when
# the dev DB restarts between requests.
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=2,
    pool_pre_ping=True,
    future=True,
)

# ``expire_on_commit=False`` keeps mapped attributes accessible after the
# session is committed, which is what FastAPI handlers typically expect.
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a per-request ``AsyncSession``.

    On success the caller is expected to commit. ``HTTPException`` is
    intentionally re-raised WITHOUT a rollback — service handlers that
    raise it (e.g. lockout, auth failure) commit the audit + state rows
    BEFORE raising, and rolling back here would erase that evidence. Any
    other exception is rolled back.
    """
    async with SessionLocal() as session:
        try:
            yield session
        except HTTPException:
            # Intentional: do not roll back the audit/state rows the
            # handler explicitly committed before raising.
            raise
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Dispose the engine on application shutdown.

    Called from the FastAPI ``lifespan`` handler so the connection pool is
    drained cleanly instead of relying on the garbage collector.
    """
    await engine.dispose()
