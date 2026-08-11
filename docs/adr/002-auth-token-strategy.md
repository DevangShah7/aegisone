# 002. Auth token strategy

- **Status:** Accepted
- **Date:** 2026-08-10

## Context

We need authentication for two distinct clients: a web browser and a native Android agent. The dashboard is a thin SPA; the Android agent is a long-lived background service.

## Decision

- **Access token:** JWT, 15-minute expiry, signed with `JWT_SECRET_KEY`. Claims: `sub`, `exp`, `iat`, `jti`, `device_id`, `scopes`.
- **Refresh token:** 30-day opaque random string, server-side, stored as `sha256` in `sessions.token_hash`. Rotated on every use; the `replaced_by` chain enables theft detection (reuse of a rotated token revokes the entire chain).
- **Web:** refresh token in an `httpOnly Secure SameSite=Lax` cookie; access token in memory only. CSRF via double-submit token.
- **Android:** device credential wrapped in Android Keystore. Refresh is held in the agent's encrypted private storage.

## Consequences

- No session-cookie awkwardness on the Android side.
- The refresh chain provides automatic revocation-on-theft detection.
- Two separate secrets, so signing an access token is impossible with the refresh secret and vice versa.
- Account enumeration is harder because the response shape and timing are constant on the login endpoint.
