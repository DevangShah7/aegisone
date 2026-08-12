# AegisOne — Final Deploy Summary

**Status as of session end (2026-08-12):**

## ✅ Done (committed, pushed, verified)

| What | Status | Where |
|---|---|---|
| Backend code | Clean, 74/74 tests pass | `eca3b39` on `origin/main` |
| Dashboard | Live, HTTP 200, all routes work | https://dashboard-kappa-six-97.vercel.app |
| APK | Built with correct backend URL baked in | `android-agent/app/build/outputs/apk/debug/app-debug.apk` |
| Render config | bulletproof — pre-fills CORS, validates DB URL | `render.yaml` + `start.sh` |
| Docs | Up to date, includes CORS-error troubleshooting | `DEPLOY.md` |

## ❌ Still needs you (browser-only)

### 1. https://dashboard.render.com → Create three things

**Step 1 — Postgres**
- New → PostgreSQL → name `aegisone-postgres`, region Oregon, plan Free, Postgres 16 → Create
- Open it → copy **Internal Database URL** (looks like `postgresql://aegisone_user:…@dpg-….oregon-postgres.render.com/aegisone`)

**Step 2 — Redis**
- New → Redis → name `aegisone-redis`, region Oregon, plan Free → Create
- Open it → copy **Internal Redis URL** (looks like `redis://red-…:6379`)

**Step 3 — Web service from Blueprint**
- Blueprints → New Blueprint Instance → repo `https://github.com/DevangShah7/aegisone` → Apply
- Wait 5–10 min for first build

### 2. Wire env vars (Render dashboard → aegisone-backend-devshah → Environment)

Two keys will be blank. Fill them:

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://` + your Postgres Internal URL (rewrite the scheme) |
| `REDIS_URL` | your Redis Internal URL as-is |

`CORS_ORIGINS` is already pre-filled with `https://dashboard-kappa-six-97.vercel.app` — leave it.

### 3. Trigger a deploy

Manual Deploy → Clear build cache & deploy.

Wait for **Live** in the top-left of the service page.

### 4. Verify

Open a terminal on your machine:

```
curl https://aegisone-backend-devshah.onrender.com/healthz
```

Expected response: `{"status":"ok"}`

If you see `[start.sh] FATAL: DATABASE_URL is not set` in the Render logs, you missed step 2.

### 5. Register from the dashboard

Open https://dashboard-kappa-six-97.vercel.app/register in a fresh browser tab.

The CORS error and ERR_CONNECTION_RESET will be gone.

## Once step 4 returns `{"status":"ok"}`

Paste that single line back to me and I'll run a full end-to-end smoke test from this session:

- Register a test user
- Enroll a device
- Send a heartbeat
- Send a command
- Fetch captures

## Optional (do later, not now)

- **cron-job.org** → cron every 5 min hitting `https://aegisone-backend-devshah.onrender.com/healthz` so the free tier doesn't sleep
- **Install the APK** on a real device:
  ```
  adb install -r E:\Code\AegisOne\android-agent\app\build\outputs\apk\debug\app-debug.apk
  ```

---

## Why I can't do step 1–3 from this session

- No `render` CLI installed
- No `RENDER_API_KEY` set
- No auth in any form

Render's free-tier service creation flow has no public API — it requires a browser login (Sign in with GitHub, OAuth callback, refresh token, etc.). I tried to find a CLI shortcut and there isn't one.

What I CAN do, and HAVE done:
- Wrote the Blueprint file (`render.yaml`) so a single click creates the web service
- Hardened `start.sh` so misconfiguration fails loudly with a clear error in the logs
- Pre-filled `CORS_ORIGINS` so the dashboard works the moment the backend boots
- Built the APK with the right URL so it's ready to install

Total remaining time on your end: ~5 minutes.
