# Testing

> **AegisOne** — Developed by Devang Shah.

## Strategy

Five layers:

1. **Unit tests** — pure-Python / pure-Kotlin / pure-TypeScript, no I/O.
2. **Integration tests** — backend ↔ Postgres ↔ Redis, in containers.
3. **Contract tests** — backend OpenAPI is the contract; dashboard and Android client tests pin to it.
4. **Security tests** — auth, authorization, rate limiting, audit logging, session revocation.
5. **End-to-end / UI tests** — happy-path user flows on the dashboard and the Android agent.

## Backend

- **Framework:** `pytest` + `pytest-asyncio` + `httpx.AsyncClient`.
- **DB:** ephemeral Postgres in CI (one per job).
- **Redis:** ephemeral Redis in CI.
- **Coverage gate:** `pytest --cov=app --cov-fail-under=70` today, raising to 80% by Milestone 3 and 90% by Milestone 6.
- **Style:** `ruff check` + `ruff format --check`. Type-check: `mypy app/`.

Tests live in `backend/tests/`. Each test file is one slice of the application:

- `test_auth.py` — register, login, refresh, logout, refresh-reuse, lockout.
- `test_health.py` — healthz / readyz / about.
- `test_rate_limit.py` — sliding window on auth endpoints.
- `test_audit.py` — every auth event writes a row.
- `test_security_headers.py` — headers on every response.
- `test_cors.py` — preflight and disallowed origins.

Run:

```bash
cd backend
pytest
pytest --cov=app --cov-fail-under=70
```

## Dashboard

- **Framework:** `vitest` for unit tests, `playwright` for end-to-end.
- **Coverage target:** 70% on the typed client + auth code.
- **Style:** `eslint` + `tsc --noEmit`.

Run:

```bash
cd dashboard
pnpm lint
pnpm typecheck
pnpm test
pnpm test:e2e
```

## Android

- **Framework:** `kotlinx.coroutines.test` + `app.cash.turbine` for unit tests.
- **UI tests:** `androidx.compose.ui.test` for Compose screens.
- **Code style:** `ktlint` + `detekt`.
- **Lint:** `gradle :app:lint`.

Run:

```bash
cd android-agent
./gradlew :app:lint :app:test :app:assembleDebug
```

## Manual QA

Documented smoke tests, run before each release:

- [ ] Register a new account, verify email.
- [ ] Logout all, log in, refresh, refresh again.
- [ ] Enroll a phone, see it on the dashboard.
- [ ] Revoke the phone, see it disappear.
- [ ] Request a screenshot via the dashboard; verify the visible indicator on the phone.
- [ ] Force-stop the agent and re-launch; verify the foreground service restarts.
- [ ] Disable network on the device; verify the agent reconnects.
- [ ] Inspect the audit log via the dashboard; verify it matches actions taken.

## Security checklist

- [ ] No `eval`, `exec`, `os.system`, or `subprocess` with user input in the backend.
- [ ] No `dangerouslySetInnerHTML` or `v-html` in the dashboard.
- [ ] Permissions in `AndroidManifest.xml` match what the code actually uses.
- [ ] No `READ_LOGS`, `ACCESSIBILITY_SERVICE`, `BIND_DEVICE_ADMIN` unless explicitly justified.
- [ ] No `WRITE_EXTERNAL_STORAGE` on Android 10+.
- [ ] `pip-audit` clean for the backend.
- [ ] `npm audit --omit=dev` clean for the dashboard.
- [ ] `gradle dependencies` reviewed for known vulnerabilities.
