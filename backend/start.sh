#!/usr/bin/env bash
# Render start script (native Python runtime).
# Render's Python runtime sets the working directory to the repo root by
# default. We `cd` to the backend directory where alembic.ini + app/ live.
set -euo pipefail

cd "$(dirname "$0")"

echo "[start.sh] cwd=$(pwd)"

# Validate critical env vars before doing anything destructive. We check
# DATABASE_URL exists and starts with a postgresql scheme (the SQLAlchemy
# async driver requires the psycopg v3 async URL, not the default
# psycopg2 one). Without this check, alembic fails with a confusing
# "could not connect to server" error.
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "[start.sh] FATAL: DATABASE_URL is not set." >&2
    echo "[start.sh] Go to Render dashboard -> aegisone-backend-devshah ->" >&2
    echo "[start.sh] Environment -> Add the Postgres Internal URL with the" >&2
    echo "[start.sh] scheme rewritten to postgresql+psycopg://" >&2
    exit 1
fi
if [[ ! "$DATABASE_URL" =~ ^postgres(ql)?(\+psycopg)?:// ]]; then
    echo "[start.sh] FATAL: DATABASE_URL scheme is '$DATABASE_URL'" >&2
    echo "[start.sh] Expected postgresql:// or postgresql+psycopg://" >&2
    exit 1
fi

echo "[start.sh] Running alembic upgrade head..."
alembic upgrade head

# Background workers (HeartbeatWorker, CommandPollWorker, etc.) are scheduled
# on the Android agent side via WorkManager — not on the backend. The backend
# is a stateless request handler; all scheduled work lives on enrolled devices.
echo "[start.sh] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
