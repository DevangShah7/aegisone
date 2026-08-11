# AegisOne Roadmap

This file tracks the public milestone plan. Internal task tracking lives in the issue tracker.

## Status

| Milestone | Scope | Status |
|---|---|---|
| 1 | Foundations + auth (backend, dashboard, android scaffolds) | **In progress** |
| 2 | Device registry + Android agent v1 | Not started |
| 3 | Command channel + core capabilities | Not started |
| 4 | Advanced agent + remote support | Not started |
| 5 | Multi-tenant + sharing | Not started |
| 6 | Hardening + release | Not started |

## Milestone 1 — Foundations + auth

- Monorepo scaffolding for `backend/`, `dashboard/`, `android-agent/`, `contracts/`, `docs/`, `infra/`, `scripts/`.
- FastAPI backend with config, structured logging, security headers middleware, Redis-backed rate limiting, health endpoints.
- Alembic migrations for `users`, `sessions`, `audit_logs`, `consents`.
- Auth: argon2id password hashing; JWT access tokens (15 min); opaque refresh tokens (30 days, rotation, chain revocation); register / login / refresh / logout / logout-all.
- Account enumeration defenses, login lockout, audit log on every auth event.
- Next.js dashboard with login + register pages, dark mode, branding footer.
- Kotlin + Compose Android scaffold with splash, Home screen, Connected/Disconnected status pill, debug build pipeline.
- Docker Compose for Postgres 16 + Redis 7 + MinIO.
- CI workflows for backend (lint + test + coverage gate + pip-audit), dashboard (tsc + eslint + next build), Android (gradle lint + test + assembleDebug).
- OpenAPI export to `contracts/openapi.json`.

**Demo:** `curl` end-to-end auth flow against running compose stack; `psql` shows audit rows; dashboard login page renders; `gradle :app:assembleDebug` produces an APK that launches and shows the splash + "Disconnected" status pill.

## Milestone 2 — Device registry + Android agent v1

- Backend: `devices`, `device_credentials`, `device_health` tables and CRUD endpoints. MinIO for file payloads. Device heartbeat endpoint. Secure pairing flow (6-digit code + QR, 5-minute TTL, single use).
- Dashboard: Devices list, Devices/[id] detail, enrollment flow with QR generation.
- Android agent: enrollment screen (scan QR / paste code), permission rationale UI, persistent foreground service, WorkManager heartbeat, device-info collector (model, OS, app version, battery, network).
- Android Keystore wraps the device credential; refresh token equivalent stored encrypted.

## Milestone 3 — Command channel + core capabilities

- Backend: WebSocket command/ack protocol with per-command auth, expiration, idempotency keys, audit log.
- Dashboard: command palette on Devices/[id].
- Android agent: command receiver (foreground service + WS), application inventory, permission audit, network diagnostics, location (Fused Location, foreground consent), screenshot via MediaProjection (visible system indicator + persistent notification + session timeout).
- File management via MinIO signed URLs (max 15 min TTL).

## Milestone 4 — Advanced agent + remote support

- Camera diagnostic (visible indicator, session timeout, audit).
- Microphone diagnostic (same).
- Contacts / Calendar / Notifications (explicit permissions; no background surveillance).
- Backup / restore (user-selected, scoped).
- Lost-device mode (lock, ring, locate).
- Screen-sharing remote-support session (MediaProjection + visible indicator + auto-timeout).
- Geofencing.
- Tamper detection (root / install-from-unknown) — reported, not enforced.

## Milestone 5 — Multi-tenant + sharing

- Organizations / teams, device groups, role-based access.
- Audit log viewer with filters + CSV/JSON export.
- Reports: PDF, CSV, JSON, TXT — all branded "AegisOne — Developed by Devang Shah".
- Privacy Center: data inventory, retention policy, soft-delete + retention TTL.
- Dashboard: settings, profile, about.

## Milestone 6 — Hardening + release

- OpenTelemetry traces, structured logs.
- Threat model document final pass.
- Production Docker image, multi-stage build, non-root user.
- Caddy / nginx reverse proxy with TLS.
- Vercel config for the dashboard.
- Backend deployment runbook.
- Release signing for Android.
- Production checklist run-through.
- Public release candidate.
