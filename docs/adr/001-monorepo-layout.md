# 001. Monorepo layout

- **Status:** Accepted
- **Date:** 2026-08-10

## Context

AegisOne has three first-class deployables: backend (FastAPI), dashboard (Next.js), and Android agent (Kotlin/Compose). They share a contract (the OpenAPI spec) and a brand identity.

## Decision

Single repository with three top-level apps, plus shared `contracts/`, `docs/`, `infra/`, `scripts/`, `.github/`. No monorepo tooling (e.g. Nx, Turborepo) at the top level — each app's own tooling is enough.

## Consequences

- OpenAPI is the single source of truth for the API contract.
- The dashboard consumes the contract via `openapi-typescript`.
- The Android agent consumes it via `openapi-generator-cli` (planned Milestone 2).
- CI is per-app, not a single matrix.
- Docker Compose lives under `infra/` so it can be extended without polluting `backend/`.
