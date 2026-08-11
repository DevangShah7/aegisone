"""FastAPI dependencies.

- ``get_db``: yields an ``AsyncSession`` from ``app.db.session.SessionLocal``.
- ``get_redis``: placeholder; wired in Milestone 1 step 9 (rate limiting).
- ``get_current_user``: decodes the bearer access token and resolves the
  user from the database. Used by protected endpoints.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AccessTokenError, decode_access_token
from app.db.session import get_db as _get_db_session

# ``auto_error=False`` so missing bearer header produces our own 401
# with consistent shape, instead of FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


# Re-exported under the name ``get_db`` so FastAPI handlers can depend on
# it without importing the database module directly.
get_db = _get_db_session


async def get_redis():  # pragma: no cover - filled in by rate-limit slice
    raise NotImplementedError("get_redis is implemented in app.middleware.rate_limit")


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _db: AsyncSession = Depends(get_db),
):
    """Resolve the access-token bearer into a dict of JWT claims.

    Returns the full claims dict (caller picks out ``sub`` / ``device_id`` /
    ``scopes``). The actual ``User`` row lookup happens in the auth slice
    — Milestone 1 step 9 — because the cookie/header contract for it is
    still being finalized.

    Raises a 401 with a generic message; we never reveal whether the token
    was malformed, expired, or simply missing.
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "missing bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(creds.credentials)
    except AccessTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "invalid access token"},
            headers={"WWW-Authenticate": "Bearer"},
        ) from err
    return claims
