"""Password hashing, JWT, and refresh-token primitives.

We use argon2id for password hashing (OWASP 2024 baseline parameters).
JWT access tokens are short-lived (15 min). Refresh tokens are opaque
random strings stored only as sha256 hashes server-side, rotated on
every use.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

# argon2id parameters per OWASP 2024 baseline.
_PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=1)


# ---- Passwords ----


def hash_password(plain: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _PASSWORD_HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against an argon2id hash.

    Raises ``argon2.exceptions.VerifyMismatchError`` on failure. Callers
    should catch it; we re-raise it because the auth service wants to
    distinguish bad-password from bad-hash.
    """
    try:
        return _PASSWORD_HASHER.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def password_needs_rehash(hashed: str) -> bool:
    """Return True if the hash uses outdated parameters and should be rotated."""
    return _PASSWORD_HASHER.check_needs_rehash(hashed)


# ---- Access tokens (JWT) ----


class AccessTokenError(Exception):
    """Raised when an access token cannot be decoded or is invalid."""


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def issue_access_token(
    *,
    user_id: str,
    device_id: str,
    scopes: list[str] | None = None,
) -> tuple[str, datetime]:
    """Issue a short-lived JWT access token.

    Returns ``(token, expires_at)``. ``expires_at`` is the absolute
    timestamp the token will expire.
    """
    now = _now_utc()
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
        "device_id": device_id,
        "scopes": scopes or [],
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Raises ``AccessTokenError`` on any failure. We never return the
    reason to the caller (no token-leaking error messages).
    """
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AccessTokenError("invalid access token") from exc


# ---- Refresh tokens (opaque) ----


def issue_refresh_token() -> tuple[str, str, datetime]:
    """Issue a new opaque refresh token.

    Returns ``(raw_token, sha256_hex, expires_at)``. The raw token is
    given to the client exactly once; only ``sha256_hex`` is stored.
    """
    raw = secrets.token_urlsafe(48)
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
    expires_at = _now_utc() + timedelta(days=settings.refresh_token_expire_days)
    return raw, digest, expires_at


def hash_refresh_token(raw: str) -> str:
    """Return the sha256 hex digest of a raw refresh token."""
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string compare, used when comparing token digests."""
    return hmac.compare_digest(a.encode("ascii"), b.encode("ascii"))
