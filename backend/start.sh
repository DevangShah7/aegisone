#!/usr/bin/env bash
# Render start script.
# 1. Run migrations (idempotent on every cold start).
# 2. Start uvicorn. Render expects the process to bind to $PORT (we map 8000 -> 8000).
set -euo pipefail

echo "[start.sh] Running alembic upgrade head..."
cd /app
alembic upgrade head

# Background workers (HeartbeatWorker, CommandPollWorker, etc.) are scheduled
# on the Android agent side via WorkManager — not on the backend. The backend
# is a stateless request handler; all scheduled work lives on enrolled devices.
echo "[start.sh] Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
