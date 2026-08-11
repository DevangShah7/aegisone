# Contributing to AegisOne

Thanks for your interest in AegisOne. This is a security-sensitive project — please read [`SECURITY.md`](SECURITY.md) before opening a pull request.

## Development setup

See [`README.md`](README.md#quick-start-local-development) for the full local-dev quick start.

## Coding standards

### Backend (Python)

- Type hints everywhere.
- `ruff` for lint and format (no arguments).
- `mypy --strict` is the target; the current module allows untyped where legacy code exists.
- All endpoints take Pydantic schemas. `extra='forbid'` on auth endpoints.
- All sensitive actions write to the audit log.
- Coverage gate is 70% today, ratcheting to 80% by Milestone 3.

### Dashboard (TypeScript / React)

- Strict TypeScript.
- ESLint + Prettier (defaults from `create-next-app`).
- Tailwind CSS, shadcn/ui for primitives.
- Keep branding in `dashboard/lib/branding.ts` — no hard-coded strings elsewhere.

### Android (Kotlin)

- Jetpack Compose for UI.
- Kotlin Coroutines + Flow for async work.
- `kotlinx.serialization` for JSON.
- Hilt for DI.
- Android Keystore for secrets.

## Pull request flow

1. Fork and branch from `main`.
2. Make your change in a topic branch with a descriptive name.
3. Run the full CI locally before pushing:
   ```bash
   cd backend && ruff check . && mypy app/ && pytest
   cd dashboard && pnpm lint && pnpm build
   cd android-agent && ./gradlew :app:lint :app:test :app:assembleDebug
   ```
4. Open a pull request against `main`. CI must be green.
5. If your change touches the API contract, regenerate `contracts/openapi.json`:
   ```bash
   python scripts/export-openapi.py
   ```
   and commit the resulting diff.

## Security-sensitive changes

Changes that touch authentication, authorization, audit logging, session management, device revocation, or any capability listed in the master prompt's sensitive-capabilities table require:

- A second reviewer.
- An entry in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).
- A changelog entry.

## Code of conduct

Be respectful. This is a security project; assume good faith from contributors and operate transparently.
