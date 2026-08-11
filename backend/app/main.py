"""AegisOne FastAPI application.

Run locally::

    cd backend
    uvicorn app.main:app --reload --port 8000

Windows note: see ``app/__main__.py`` for ``python -m app`` which
installs the Windows-compatible selector event loop before uvicorn
starts. ``uvicorn app.main:app`` directly on Windows will fail with a
psycopg ``ProactorEventLoop`` error because uvicorn's default Windows
loop factory is incompatible with the psycopg v3 driver.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import activity, auth, devices, health, users

logger = logging.getLogger(__name__)

# Default-sentinel for the bootstrap "user forgot to set the secret" check.
# Matches the placeholder in core/config.py. Must be a stable string so the
# lifespan check below is deterministic.
_JWT_DEV_SENTINEL = "AEGISONE_DEV_ONLY_REPLACE_ME_!!!"  # noqa: S105


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Application lifespan.

    Runs once on startup and once on shutdown. We use it to enforce
    production invariants before the first request lands and to
    configure logging exactly once.
    """
    configure_logging(settings.log_level)

    if settings.environment == "production":
        if (
            settings.jwt_secret_key == _JWT_DEV_SENTINEL
            or settings.jwt_refresh_secret_key == _JWT_DEV_SENTINEL
        ):
            raise RuntimeError(
                "JWT_SECRET_KEY and JWT_REFRESH_SECRET_KEY must be set in production."
            )
        if "*" in settings.cors_origins:
            raise RuntimeError("CORS_ORIGINS must not include '*' in production.")

    logger.info(
        "AegisOne backend starting (environment=%s, version=%s, developer=%s)",
        settings.environment,
        settings.app_version,
        settings.developer_name,
    )
    yield
    logger.info("AegisOne backend shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AegisOne",
        description=(
            "AegisOne — Secure Remote Device Management for device owners and "
            "authorized operators.\n\n"
            "**Developed by Devang Shah.**"
        ),
        version=settings.app_version,
        contact={
            "name": settings.developer_name,
            "url": "https://github.com/aegisone",
        },
        license_info={"name": "MIT"},
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware order matters:
    # - CORS first so it short-circuits OPTIONS preflights before any
    #   other middleware touches them.
    # - request-id so every log line carries it.
    # - security headers last so they apply to all responses including
    #   CORS preflight responses.
    allow_origins = settings.cors_origins_list
    allow_credentials = any(o != "*" for o in allow_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "Accept",
        ],
        max_age=600,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(users.router, prefix="/users", tags=["users"])
    app.include_router(devices.router, prefix="/devices", tags=["devices"])
    app.include_router(activity.router, prefix="/activity", tags=["activity"])

    return app


app = create_app()
