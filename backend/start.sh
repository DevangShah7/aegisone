#!/usr/bin/env bash
# Render start script (native Python runtime).
# Render's Python runtime sets the working directory to the repo root by
# default. We `cd` to the backend directory where alembic.ini + app/ live.
set -euo pipefail

cd "$(dirname "$0")"

echo "[start.sh] cwd=$(pwd)"
echo "[start.sh] Running alembic upgrade head..."
alembic upgrade head

# Background workers (HeartbeatWorker, CommandPollWorker, etc.) are scheduled
# on the Android agent side via WorkManager — not on the backend. The backend
# is a stateless request handler; all scheduled work lives on enrolled devices.
echo "[start.sh] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
