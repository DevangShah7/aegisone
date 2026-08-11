"""Health, readiness, and about endpoints.

- ``GET /healthz`` — liveness; 200 if the process is up.
- ``GET /readyz`` — readiness; 200 if Postgres and Redis respond.
- ``GET /about`` — version metadata, sourced from settings (no secrets).

These endpoints are intentionally minimal and unauthenticated.
"""

from __future__ import annotations

import logging
import platform
import sys
from typing import Any

from fastapi import APIRouter, Request, Response

from app.core.config import settings

router = APIRouter(tags=["health"])
_log = logging.getLogger(__name__)


@router.get("/healthz", summary="Liveness check")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness check (Postgres + Redis)")
async def readyz(request: Request, response: Response) -> dict[str, Any]:
    """Real implementation arrives when Postgres and Redis clients are wired.

    For Milestone 1 we return 200 with explicit dependencies so the
    compose stack can prove connectivity at the TCP layer via Docker
    healthchecks. Once the auth slice lands this returns 503 if any
    dependency is unreachable.
    """
    return {
        "status": "ok",
        "dependencies": {
            "postgres": "pending",
            "redis": "pending",
        },
    }


@router.get("/about", summary="About AegisOne")
async def about() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "tagline": settings.app_tagline,
        "developer": settings.developer_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
