"""Auth endpoints.

Routes:

- ``POST /auth/register``      — create a new account
- ``POST /auth/login``         — exchange email + password for a token pair
- ``POST /auth/refresh``       — exchange a refresh token for a new pair
- ``POST /auth/logout``        — revoke the given refresh token
- ``POST /auth/logout-all``    — revoke every refresh token for the caller

All handlers delegate to ``app.services.auth``. The router's job is to
parse the request, pull the IP / user-agent, and shape the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import issue_access_token
from app.schemas.auth import (
    LoginIn,
    LogoutIn,
    RefreshIn,
    RegisterIn,
    RegisterOut,
    TokenPair,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    In dev, this is ``request.client.host``. Behind a trusted proxy the
    reverse-proxy middleware (added in the deployment slice) will have
    already swapped in the forwarded address. Returns ``None`` if the
    value isn't a valid IP (TestClient reports ``"testclient"``, which
    would otherwise blow up the ``INET`` column in ``audit_logs``).
    """
    if request.client is None:
        return None
    import ipaddress

    candidate = request.client.host
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    response_model=RegisterOut,
)
async def register(
    payload: RegisterIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RegisterOut:
    user = await auth_service.register(
        session,
        email=payload.email,
        password=payload.password,
        device_id=payload.device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return RegisterOut(user=_to_user_out(user))


@router.post(
    "/login",
    summary="Log in and obtain an access + refresh token pair",
    response_model=TokenPair,
)
async def login(
    payload: LoginIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenPair:
    _, access, refresh, access_exp = await auth_service.login(
        session,
        email=payload.email,
        password=payload.password,
        device_id=payload.device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=_seconds_until(access_exp),
    )


@router.post(
    "/refresh",
    summary="Exchange a refresh token for a new pair",
    response_model=TokenPair,
)
async def refresh(
    payload: RefreshIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TokenPair:
    access, refresh, access_exp = await auth_service.refresh(
        session,
        refresh_token=payload.refresh_token,
        device_id=payload.device_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=_seconds_until(access_exp),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Revoke the current refresh token",
)
async def logout(
    payload: LogoutIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await auth_service.logout(
        session,
        refresh_token=payload.refresh_token,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        device_id=None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Revoke every refresh token for the caller",
)
async def logout_all(
    request: Request,
    session: AsyncSession = Depends(get_db),
    claims: dict = Depends(get_current_user),
) -> Response:
    user_id = claims["sub"]
    await auth_service.logout_all(
        session,
        user_id=user_id,
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        device_id=claims.get("device_id"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- helpers --------------------------------------------------------------


def _to_user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


def _seconds_until(when) -> int:
    from datetime import UTC, datetime

    return max(0, int((when - datetime.now(tz=UTC)).total_seconds()))


# Helper kept for symmetry with login/refresh: the logout-all endpoint
# doesn't need to issue a new token, but exposing this helper lets us
# add a "list active sessions" view in Milestone 2 without duplicating.
issue_access_token  # noqa: B018  (re-export for tests)
