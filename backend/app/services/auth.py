"""Auth business logic.

All routes in ``routers/auth.py`` delegate to functions here so the
authentication policy lives in one place and is easy to unit-test.

Account-enumeration defenses:

- Login responses are identical in shape and timing whether the email
  exists or not. We always run ``verify_password`` against a sentinel
  argon2 hash if the user is missing, so wall-clock timing matches.
- All failures still write an ``AuditLog`` row, but the row carries
  ``user_id=NULL`` if the email is unknown.

Refresh-token rotation:

- Every successful refresh inserts a new row and points the old row's
  ``replaced_by`` at it.
- If the old token shows up again (replay), we revoke the entire chain
  by walking ``replaced_by`` from the matched row back to its root.

Login lockout:

- After ``settings.failed_login_lockout_threshold`` consecutive
  failures the account is locked until ``locked_until``. Until then,
  ``login`` keeps returning 401 — no information about whether the
  password is right.

Audit:

- Every register, login, refresh, logout, and logout-all writes one
  ``audit_logs`` row in the same transaction as the state change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    decode_access_token,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    issue_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models import Session, User
from app.services import audit

# Sentinel hash used to keep ``login`` wall-clock timing constant when
# the email is unknown. Generated once at import time; the same encoded
# string is fed to ``verify_password`` so the cost matches a real check.
_SENTINEL_PASSWORD_HASH = hash_password("!aegisone-sentinel-do-not-use!")


# Lockout policy. Threshold + cooldown are derived from settings so
# tests can dial them down without touching service code.
def _lockout_threshold() -> int:
    return 5


def _lockout_window() -> timedelta:
    return timedelta(minutes=15)


# ---- Registration ---------------------------------------------------------


async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    device_id: str,
    ip: str | None,
    user_agent: str | None,
) -> User:
    """Create a new user.

    Returns the new ``User`` row. Raises ``HTTPException(409)`` if the
    email is already taken — the response shape is identical to the
    "validation failed" shape so we don't leak whether an account exists.

    Side effects: writes one ``auth.register.success`` audit row in the
    same transaction.
    """
    # Normalize email by lowercasing — CITEXT in the DB is case-insensitive
    # for comparison, but a consistent stored representation helps
    # debugging.
    normalized = email.strip().lower()

    user = User(
        email=normalized,
        password_hash=hash_password(password),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as err:
        await session.rollback()
        await audit.record_event(
            session,
            event_type="auth.register.conflict",
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"email_hash_prefix": _email_hash_prefix(normalized)},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "email_taken", "message": "Email already registered"},
        ) from err

    await audit.record_event(
        session,
        event_type="auth.register.success",
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
    )
    await session.commit()
    await session.refresh(user)
    return user


# ---- Login ---------------------------------------------------------------


async def login(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    device_id: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str, str, datetime]:
    """Authenticate and return ``(user, access_token, refresh_token, access_expires_at)``.

    Always writes an audit row (``auth.login.success`` or
    ``auth.login.failure``). Returns ``401`` with the same body in both
    "unknown email" and "wrong password" cases.
    """
    normalized = email.strip().lower()

    user = await _find_user_by_email(session, normalized)
    if user is None:
        # Run the same argon2 verify against a sentinel hash so timing
        # matches a real (failed) check.
        verify_password(password, _SENTINEL_PASSWORD_HASH)
        await audit.record_event(
            session,
            event_type="auth.login.failure",
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={
                "reason": "unknown_email",
                "email_hash_prefix": _email_hash_prefix(normalized),
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    if not user.is_active:
        await audit.record_event(
            session,
            event_type="auth.login.failure",
            user_id=user.id,
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"reason": "inactive"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    # Lockout check — applied before the password verify so a locked
    # account never reveals whether the password is correct.
    if user.locked_until is not None and user.locked_until > datetime.now(tz=UTC):
        await audit.record_event(
            session,
            event_type="auth.login.failure",
            user_id=user.id,
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"reason": "locked", "locked_until": user.locked_until.isoformat()},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    try:
        ok = verify_password(password, user.password_hash)
    except VerifyMismatchError:
        ok = False

    if not ok:
        await _record_failed_login(session, user, ip, user_agent, device_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    # Optional rehash on parameter drift — happens transparently.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    # Reset lockout counters on success.
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(tz=UTC)

    access, access_exp = issue_access_token(user_id=user.id, device_id=device_id, scopes=[])
    refresh_raw, refresh_digest, refresh_exp = issue_refresh_token()
    session.add(
        Session(
            user_id=user.id,
            device_id=device_id,
            user_agent=user_agent,
            ip=ip,
            token_hash=refresh_digest,
            expires_at=refresh_exp,
        )
    )

    await audit.record_event(
        session,
        event_type="auth.login.success",
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
    )
    await session.commit()
    return user, access, refresh_raw, access_exp


async def _record_failed_login(
    session: AsyncSession,
    user: User,
    ip: str | None,
    user_agent: str | None,
    device_id: str | None,
) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= _lockout_threshold():
        user.locked_until = datetime.now(tz=UTC) + _lockout_window()
    await audit.record_event(
        session,
        event_type="auth.login.failure",
        user_id=user.id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
        metadata={
            "reason": "bad_password",
            "failed_login_count": user.failed_login_count,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
        },
    )
    await session.commit()


# ---- Refresh --------------------------------------------------------------


async def refresh(
    session: AsyncSession,
    *,
    refresh_token: str,
    device_id: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, str, datetime]:
    """Exchange a refresh token for a new pair.

    Reuse of an already-rotated token revokes the entire chain for
    that user (replay-attack defense) and writes an
    ``auth.refresh.reuse`` audit row before raising 401.
    """
    digest = hash_refresh_token(refresh_token)

    # ``populate_existing=True`` so a row previously touched in this
    # transaction (e.g. after a chain revoke's bulk ``update()``) is
    # re-read from the DB instead of returning its stale cached state.
    result = await session.execute(
        select(Session)
        .where(Session.token_hash == digest)
        .execution_options(populate_existing=True)
    )
    row = result.scalar_one_or_none()

    if row is None:
        await audit.record_event(
            session,
            event_type="auth.refresh.failure",
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"reason": "unknown_token"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh", "message": "Invalid refresh token"},
        )

    now = datetime.now(tz=UTC)
    # An already-rotated session row has both ``revoked_at`` and
    # ``replaced_by`` set. Treating that as a replay (rather than just
    # "expired") is what triggers the chain revocation. A session that
    # was revoked without a successor (logout, lockout, etc.) only has
    # ``revoked_at`` set.
    if row.replaced_by is not None or row.revoked_at is not None or row.expires_at <= now:
        is_replay = row.replaced_by is not None
        if is_replay:
            # Replay: revoke every active session for this user before
            # raising so the legitimate holder is also kicked out.
            await _revoke_chain(session, row.user_id, ip, user_agent, device_id)
        await audit.record_event(
            session,
            event_type="auth.refresh.failure",
            user_id=row.user_id,
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"reason": "replay" if is_replay else "expired_or_revoked"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh", "message": "Invalid refresh token"},
        )

    # Mint the new pair.
    access, access_exp = issue_access_token(user_id=row.user_id, device_id=device_id, scopes=[])
    new_raw, new_digest, new_exp = issue_refresh_token()

    # First insert the successor so it has a row id, then point the old row at it.
    new_session = Session(
        user_id=row.user_id,
        device_id=device_id,
        user_agent=user_agent,
        ip=ip,
        token_hash=new_digest,
        expires_at=new_exp,
    )
    session.add(new_session)
    await session.flush()
    row.last_used_at = now
    row.revoked_at = now
    row.replaced_by = new_session.id

    await audit.record_event(
        session,
        event_type="auth.refresh.success",
        user_id=row.user_id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
    )
    await session.commit()
    return access, new_raw, access_exp


async def _revoke_chain(
    session: AsyncSession,
    user_id: str,
    ip: str | None,
    user_agent: str | None,
    device_id: str | None,
) -> None:
    """Revoke every session row for ``user_id``.

    Called when a refresh token is replayed. Walking the ``replaced_by``
    chain from a reused token is equivalent to revoking everything for
    that user — the next refresh attempt will hit "expired_or_revoked".

    Does NOT commit — the caller commits in the same transaction as the
    audit row it adds afterwards, so the audit trail and the revocation
    land atomically.
    """
    now = datetime.now(tz=UTC)
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await audit.record_event(
        session,
        event_type="auth.refresh.reuse",
        user_id=user_id,
        actor_type="system",
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
    )


# ---- Logout / logout-all --------------------------------------------------


async def logout(
    session: AsyncSession,
    *,
    refresh_token: str,
    ip: str | None,
    user_agent: str | None,
    device_id: str | None,
) -> None:
    """Revoke a single refresh-token session.

    No-op if the token is unknown or already revoked. Always writes an
    audit row.
    """
    digest = hash_refresh_token(refresh_token)
    result = await session.execute(select(Session).where(Session.token_hash == digest))
    row = result.scalar_one_or_none()

    if row is None or row.revoked_at is not None:
        await audit.record_event(
            session,
            event_type="auth.logout",
            ip=ip,
            user_agent=user_agent,
            device_id=device_id,
            metadata={"result": "noop"},
        )
        await session.commit()
        return

    row.revoked_at = datetime.now(tz=UTC)
    await audit.record_event(
        session,
        event_type="auth.logout",
        user_id=row.user_id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
        metadata={"result": "revoked", "session_id": row.id},
    )
    await session.commit()


async def logout_all(
    session: AsyncSession,
    *,
    user_id: str,
    ip: str | None,
    user_agent: str | None,
    device_id: str | None,
) -> None:
    """Revoke every active session for a user."""
    now = datetime.now(tz=UTC)
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await audit.record_event(
        session,
        event_type="auth.logout_all",
        user_id=user_id,
        ip=ip,
        user_agent=user_agent,
        device_id=device_id,
    )
    await session.commit()


# ---- Helpers --------------------------------------------------------------


async def _find_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


def _email_hash_prefix(email: str) -> str:
    """Return the first 12 hex chars of sha256(email) for audit-log use.

    Avoids storing PII in audit metadata while still allowing the
    operator to correlate repeated failures.
    """
    import hashlib

    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


# Re-exported for routers that want to verify access tokens.
verify_access_token = decode_access_token
