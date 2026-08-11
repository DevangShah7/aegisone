"""Auth DTOs.

Every request schema here has ``extra='forbid'`` so unknown fields are
rejected with a 422. Password length minimum matches the master prompt
("Min length 12. No composition rules.").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---- Requests ----


class RegisterIn(BaseModel):
    """POST /auth/register body."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # OWASP 2024 baseline: ≥12 chars, no composition rules. Max length
    # is bounded to prevent an attacker from forcing argon2 over an
    # enormous string (which would DoS the request worker).
    password: str = Field(min_length=12, max_length=256)
    # Client-supplied device id; opaque to the server.
    device_id: str = Field(min_length=1, max_length=128)


class LoginIn(BaseModel):
    """POST /auth/login body."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    """POST /auth/refresh body."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=512)
    device_id: str = Field(min_length=1, max_length=128)


class LogoutIn(BaseModel):
    """POST /auth/logout body."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=20, max_length=512)


# ---- Responses ----


class UserOut(BaseModel):
    """Public user profile — never includes ``password_hash`` or lockout state."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    created_at: str


class RegisterOut(BaseModel):
    """POST /auth/register response."""

    model_config = ConfigDict(extra="forbid")

    user: UserOut


class TokenPair(BaseModel):
    """Access + refresh token pair returned by login and refresh."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    # Lifetime in seconds — clients use it to schedule refreshes.
    expires_in: int
    token_type: str = "Bearer"  # noqa: S105 - per RFC 6750
