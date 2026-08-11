# AegisOne

**Secure Remote Device Management** for device owners and authorized operators.

> Secure. Manage. Protect.
>
> **Developed by Devang Shah**

AegisOne is a consent-based, transparent remote device management, diagnostics, remote-support, backup, and security platform. It consists of:

- **AegisOne Android Agent** — installed on a device that has been explicitly enrolled by its owner.
- **AegisOne Control Center** — a modern web dashboard for managing authorized/enrolled devices.
- **AegisOne Backend** — a secure API responsible for authentication, device enrollment, authorization, telemetry, commands, synchronization, audit logs, and reporting.

The platform is built around three non-negotiable principles:

1. **Explicit consent.** Every device is enrolled by its owner. Every sensitive capability is approved by that owner on the device, through the operating system's permission model, with visible system indicators.
2. **No covert operation.** No hidden cameras, microphones, screen capture, credential theft, or stealth persistence. Sensitive operations use the platform's official APIs and surface a system indicator when active.
3. **Auditability.** Every sensitive action is logged. Sessions are revocable. Devices can be disconnected at any time.

See [`SECURITY.md`](SECURITY.md) for the threat model and vulnerability disclosure, [`ROADMAP.md`](ROADMAP.md) for the milestone plan, and [`docs/`](docs/) for deeper documentation.

## Repository layout

```
aegisone/
├── backend/          FastAPI service (Python)
├── dashboard/        Next.js web Control Center (TypeScript)
├── android-agent/    Kotlin Android agent (Jetpack Compose)
├── contracts/        Generated OpenAPI artifact (single source of truth)
├── docs/             Architecture, security, privacy, deployment, testing
├── infra/            docker-compose, reverse proxy config
├── scripts/          Local dev helpers (secrets, openapi export)
└── .github/          CI workflows
```

## Quick start (local development)

Prerequisites: Docker, Python 3.12+, Node.js 20+, pnpm 9+, JDK 17+ (for Android).

```bash
# 1. Clone
git clone <repo-url> aegisone
cd aegisone

# 2. Generate secrets for the backend
python scripts/gen-secrets.py

# 3. Start the dev stack
docker compose -f infra/docker-compose.yml up -d

# 4. Run the backend locally (auto-reload)
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head

# On Linux / macOS:
uvicorn app.main:app --reload --port 8000

# On Windows:
# ``python -m app`` is a Windows-aware launcher that patches uvicorn's
# default ``ProactorEventLoop`` factory to ``SelectorEventLoop`` so the
# psycopg v3 driver can connect. Without it, every request that touches
# the database fails with ``InterfaceError: Psycopg cannot use the
# 'ProactorEventLoop'``.
python -m app

# 5. Run the dashboard
cd ../dashboard
pnpm install
pnpm dev

# 6. Build the Android agent
cd ../android-agent
./gradlew :app:assembleDebug
```

Verify:

- `curl http://localhost:8000/healthz` → 200
- `curl http://localhost:8000/readyz` → 200 (after Postgres/Redis come up)
- `curl http://localhost:8000/about` → JSON with `"developer": "Devang Shah"`
- http://localhost:3000 → AegisOne login page
- `app/build/outputs/apk/debug/app-debug.apk` → installable on an Android device or emulator

## Generating the OpenAPI contract

The dashboard and the Android agent consume the same OpenAPI artifact —
`contracts/openapi.json` is the single source of truth for the public
HTTP API. After changing a router, schema, or response model:

```bash
# from the repo root, with the backend venv activated
PYTHONPATH=backend python scripts/export-openapi.py          # write
PYTHONPATH=backend python scripts/export-openapi.py --check  # CI drift check
```

`--check` exits non-zero if the on-disk file is stale, so wrap it in a
pre-commit hook or rely on `backend-ci.yml`, which runs both commands
on every PR.

## Production

- Dashboard: deploy to Vercel (or any static host).
- Backend: deploy to a long-running host (Fly.io, Render, a VM, or container platform). Do not deploy the backend to Vercel Functions — long-lived WebSocket connections and database pooling require a persistent process.
- TLS is terminated at the reverse proxy (Caddy / nginx). The backend trusts `X-Forwarded-Proto` from a configurable allowlist.

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full runbook.

## License

See [`LICENSE`](LICENSE).
