"""Authentication and authorization primitives tests.

These tests cover the password hashing, JWT, and refresh-token helpers
in isolation. The full /auth/* flow tests arrive with the auth slice.
"""

from __future__ import annotations

import time

import pytest

from app.core.security import (
    AccessTokenError,
    constant_time_equals,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    issue_refresh_token,
    password_needs_rehash,
    verify_password,
)


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong", hashed) is False


def test_hash_is_argon2id() -> None:
    hashed = hash_password("a")
    assert hashed.startswith("$argon2id$")


def test_issue_and_decode_access_token_roundtrip() -> None:
    token, expires_at = issue_access_token(
        user_id="00000000-0000-0000-0000-000000000001",
        device_id="dev-1",
        scopes=["read"],
    )
    claims = decode_access_token(token)
    assert claims["sub"] == "00000000-0000-0000-0000-000000000001"
    assert claims["device_id"] == "dev-1"
    assert claims["scopes"] == ["read"]
    assert claims["exp"] == int(expires_at.timestamp())


def test_decode_access_token_rejects_garbage() -> None:
    with pytest.raises(AccessTokenError):
        decode_access_token("not-a-real-token")


def test_issue_refresh_token_returns_distinct_pairs() -> None:
    a = issue_refresh_token()
    b = issue_refresh_token()
    assert a[0] != b[0]
    assert a[1] != b[1]
    assert a[0] != a[1]


def test_hash_refresh_token_is_sha256_hex() -> None:
    raw, digest, _ = issue_refresh_token()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert hash_refresh_token(raw) == digest


def test_constant_time_equals_works() -> None:
    assert constant_time_equals("abc", "abc") is True
    assert constant_time_equals("abc", "abd") is False
    assert constant_time_equals("abc", "abcd") is False


def test_password_needs_rehash_is_boolean() -> None:
    hashed = hash_password("x")
    assert isinstance(password_needs_rehash(hashed), bool)


@pytest.mark.parametrize(
    "secret",
    ["short", "no_special_Aa1", "123456789012"],
)
def test_short_passwords_still_hash_but_rely_on_validator(secret: str) -> None:
    """The hashing primitive does not enforce length itself — that's a
    schema concern in the auth slice. We just make sure hashing doesn't
    blow up on short input."""
    hashed = hash_password(secret)
    assert hashed.startswith("$argon2id$")
    assert verify_password(secret, hashed) is True


def test_access_token_has_short_lifetime() -> None:
    """The default access-token lifetime must stay under 1 day."""
    _, expires_at = issue_access_token(user_id="x", device_id="y")
    lifetime = expires_at.timestamp() - time.time()
    assert 0 < lifetime < 60 * 60 * 24
