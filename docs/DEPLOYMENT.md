# Deployment

> **AegisOne** — Developed by Devang Shah.

This is the production deployment runbook. Local development setup is in [`README.md`](../README.md).

## Topology

```
              +----------+
              | Vercel   |  AegisOne dashboard (Next.js)
              |   CDN    |
              +----+-----+
                   |
                   | HTTPS (browser -> dashboard API)
                   |
                   v
        +----------+----------+
        | Reverse proxy       |  TLS termination (Caddy or nginx)
        | (Caddy / nginx)     |
        +----------+----------+
                   |
        +----------+----------+        +----------------+
        | AegisOne backend    | -----> | PostgreSQL 16  |
        | (FastAPI + uvicorn) |        +----------------+
        | on Fly.io / Render  |        +----------------+
        | / a VM / K8s        | -----> | Redis 7        |
        +----------+----------+        +----------------+
                   |
                   | S3 API
                   v
        +----------+----------+
        | MinIO (S3)          |  OR AWS S3 / Cloudflare R2
        | Object storage      |
        +---------------------+
```

## Backend

### Build

```bash
cd backend
docker build -t aegisone-backend:<tag> .
```

Multi-stage `Dockerfile` (in `backend/`):

- Builder stage: `python:3.12-slim`, install build deps, install package into `/install`.
- Runtime stage: `python:3.12-slim`, copy `/install`, non-root user, no shell, `HEALTHCHECK` calling `/healthz`.

### Run

```bash
docker run -d \
  --name aegisone-backend \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  -e JWT_SECRET_KEY=... \
  -e JWT_REFRESH_SECRET_KEY=... \
  -e CORS_ORIGINS=https://dashboard.example.com \
  -e TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16 \
  aegisone-backend:<tag>
```

The backend will refuse to boot in `ENVIRONMENT=production` if `JWT_SECRET_KEY` or `JWT_REFRESH_SECRET_KEY` is unset, or if `CORS_ORIGINS` is `*`.

### Migrations

Run as a one-off job before / during the deploy:

```bash
docker run --rm \
  -e DATABASE_URL=$DATABASE_URL \
  aegisone-backend:<tag> \
  alembic upgrade head
```

### Health checks

- `/healthz` — process liveness. 200 if the process is up.
- `/readyz` — readiness. 200 only if Postgres and Redis respond.
- `/about` — version metadata.

Configure the orchestrator's liveness probe to hit `/healthz` every 30 seconds; readiness probe to hit `/readyz` every 10 seconds.

### TLS

Do not terminate TLS in the backend. The reverse proxy in front of the backend handles TLS. The backend trusts `X-Forwarded-Proto` from `TRUSTED_PROXIES` and rejects other forwarded headers.

## Dashboard

### Build

```bash
cd dashboard
pnpm install --frozen-lockfile
pnpm build
```

### Deploy to Vercel

We recommend `vercel.ts` configuration:

```ts
// dashboard/vercel.ts
import { framework, type VercelConfig } from '@vercel/config/v1';

export const config: VercelConfig = {
  framework: 'nextjs',
  buildCommand: 'pnpm build',
  env: {
    NEXT_PUBLIC_API_BASE_URL: 'https://api.aegisone.example.com',
  },
};
```

Set the following in Vercel:

- `NEXT_PUBLIC_API_BASE_URL` — `https://api.aegisone.example.com`
- `AUTH_SECRET` — long random string for Auth.js session token signing

Do **not** put backend secrets in Vercel env vars that are exposed to the browser.

## Reverse proxy (Caddy example)

```caddy
api.aegisone.example.com {
  reverse_proxy backend:8000
  encode zstd gzip
}
```

## Database

- Use a managed Postgres (e.g. Supabase, Neon, RDS) for production.
- TLS required on the connection.
- A separate non-superuser role for the backend.
- Daily snapshot backups; 7-day retention at minimum.
- Run `alembic upgrade head` as a release step. Never run migrations inside an application container in a way that races startup.

## Redis

- Use a managed Redis (Upstash, Redis Cloud, ElastiCache).
- TLS required.
- `maxmemory-policy noeviction` (we don't want silent cache evictions to break rate limiting).
- ACL: a single user with limited command set (no `FLUSHALL`, no `CONFIG`).

## Object storage

- MinIO for self-hosted, or AWS S3 / Cloudflare R2 for managed.
- Bucket is private. No `s3:PutBucketPolicy`.
- Signed URLs are issued by the backend and capped at 15 minutes.
- Max upload size enforced at the backend (e.g. 100 MB) before the client is given a signed URL.

## Android release

- Generate a release keystore (NOT committed to the repo).
- `gradle.properties` credentials are read from env vars.
- Build with `./gradlew :app:bundleRelease`.
- Sign with the upload key from Google Play Console.

## Order of operations (greenfield)

1. Provision Postgres, Redis, MinIO (or S3-compatible).
2. Deploy backend; run `alembic upgrade head`.
3. Configure DNS + reverse proxy + TLS.
4. Deploy dashboard to Vercel.
5. Build and sign the Android AAB; upload to Google Play Console (internal testing first).
6. Run the production checklist from [`ROADMAP.md`](../ROADMAP.md#milestone-6--hardening--release).
