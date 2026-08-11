# Architecture

> **AegisOne** — Developed by Devang Shah.

## Overview

AegisOne is a three-tier system:

```
                     +---------------------+
                     |     Web Browser     |
                     |  (AegisOne Control  |
                     |      Center)        |
                     +----------+----------+
                                |
                       HTTPS    |    WebSocket
                                |
+---------------+      +--------v----------+      +-----------------+
| Android Agent | <--> |  AegisOne Backend | <--> |  PostgreSQL 16  |
| (Kotlin/Compose)     |  (FastAPI / Py)   |      +-----------------+
                       |                   |      +-----------------+
                       |                   | <--> |    Redis 7      |
                       |                   |      +-----------------+
                       |                   |      +-----------------+
                       |                   | <--> | MinIO (S3)      |
                       +-------------------+      +-----------------+
```

## Components

### Backend (`backend/`)

- **FastAPI** service written in Python 3.12+.
- **Async** request handling with `uvicorn` and `httpx`.
- **SQLAlchemy 2.x** ORM with `asyncpg` driver.
- **Alembic** for migrations.
- **PostgreSQL 16** for primary storage.
- **Redis 7** for rate limiting and short-lived caches.
- **MinIO** for object storage (S3-compatible).
- **OpenAPI** auto-generated; dumped to `contracts/openapi.json` for downstream consumers.

### Dashboard (`dashboard/`)

- **Next.js 14** with the App Router.
- **TypeScript**, strict mode.
- **Tailwind CSS** + **shadcn/ui** for components.
- **TanStack Query** for server state.
- **`openapi-typescript`** generates a typed client from `contracts/openapi.json`.
- **Auth.js (NextAuth)** cookie-based session bridge to the backend's bearer tokens.

### Android agent (`android-agent/`)

- **Kotlin** + **Jetpack Compose**.
- **MVVM** with `ViewModel` + `StateFlow`.
- **Hilt** for DI.
- **Retrofit + OkHttp** for HTTP, OkHttp WebSocket for the command channel.
- **Room** for local persistence.
- **WorkManager** for periodic heartbeat + sync.
- **Android Keystore** for the device credential.
- **BiometricPrompt** for sensitive local actions.

## Data flow

1. **Enrollment.** The device owner scans a QR code from the dashboard or types a 6-digit pairing code. The Android agent presents a consent screen, requests the minimum permissions, and registers the device with the backend. The device receives a long-lived credential stored in the Android Keystore.
2. **Heartbeat.** A `WorkManager` periodic worker sends device health (battery, network, app version) to the backend every N minutes.
3. **Command.** The dashboard issues a command. The backend stores it, audit-logs it, and pushes it to the device via the WebSocket channel. The device returns an ack (and a result for queries), which the backend records and surfaces to the dashboard.
4. **Sensitive capabilities.** Camera, microphone, screen capture, location, contacts, calendar, notifications, and SMS all require explicit Android runtime permission and surface a visible system indicator. The agent never invokes them in the background.
5. **Revocation.** The dashboard can revoke a device or a session. The backend deletes the device credential and broadcasts a revocation over the WebSocket. The agent on the device wipes its local Keystore entry and refuses further commands.

## Auth model

- **Access token.** JWT, 15 minutes, signed with `JWT_SECRET_KEY`. Claims: `sub`, `exp`, `iat`, `jti`, `device_id`, `scopes`.
- **Refresh token.** Opaque random string, 30 days, stored as `sha256` in `sessions.token_hash`. Rotated on every use; reuse revokes the entire chain.
- **Web dashboard.** Refresh token stored in an `httpOnly Secure SameSite=Lax` cookie. Access token in memory. CSRF via double-submit token.
- **Android agent.** Device credential stored in Android Keystore. Refresh token equivalent never leaves the device except during explicit auth requests.

## Deployment

- **Dashboard** → Vercel (or any static host).
- **Backend** → a long-running host (Fly.io, Render, a VM, or container platform). The backend is not deployed to Vercel Functions because of long-lived WebSocket connections and database pooling.
- **TLS** → terminated at the reverse proxy (Caddy / nginx). The backend trusts `X-Forwarded-Proto` from a configurable allowlist.
- **Android** → signed AAB distributed via the Play Store (after enterprise-track approval) or sideload / F-Droid for the open build.

## Boundaries

| Boundary | Threat | Control |
|---|---|---|
| Browser ↔ Backend | XSS, CSRF, MITM | HTTPS, HSTS, CSP, httpOnly cookies, double-submit CSRF |
| Android ↔ Backend | MITM, replay, credential theft | TLS, signed refresh tokens, chain revocation, Android Keystore |
| Backend ↔ Postgres | SQL injection, credential theft | SQLAlchemy parameterized queries, ephemeral credentials, separate DB user per service |
| Backend ↔ Redis | Command injection, credential theft | Parameterized commands, TLS, separate user |
| Backend ↔ MinIO | Signed URL leakage, public bucket | Private bucket, max 15-min signed URLs, deny `s3:PutBucketPolicy` |
| Tenant isolation | Cross-tenant data exposure | Row-level security (planned Milestone 5) |

## Open questions

- Row-level security on Postgres vs. application-layer enforcement: deferred to Milestone 5 when multi-tenant lands.
- WebSocket fan-out: in-memory pub/sub vs. Redis pub/sub. Start in-memory; switch to Redis when we run multiple backend instances.
- End-to-end encryption for sensitive payloads (screen captures, location). Add a deferred ADR when the use case is clear.
