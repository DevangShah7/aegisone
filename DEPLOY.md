# AegisOne — Free-Tier Production Deploy

Slice 2 production deploy on **Render (backend + Postgres + Redis)** and **Vercel (dashboard)**, both on free tiers. APK rebuilt against the live Render URL.

Total monthly cost: **$0**.

---

## Prerequisites (one-time)

- A **GitHub** account (you have one: `DevangShah7`).
- A **Render** account — sign up at https://render.com using the "Sign in with GitHub" button.
- A **Vercel** account — sign up at https://vercel.com using "Sign in with GitHub".
- A **cron-job.org** account — sign up at https://cron-job.org (free). Used to keep the Render free service awake.
- A **GitHub personal access token** with `repo` scope (only if you're not already authed to GitHub on this machine).

---

## Step 1 — Push code to GitHub

```powershell
cd E:\Code\AegisOne
git init
git add .
git commit -m "AegisOne slice 2 — free-tier deploy"
git branch -M main
git remote add origin https://github.com/DevangShah7/aegisone.git
git push -u origin main
```

If the repo doesn't exist yet, create it at https://github.com/new first (public, name `aegisone`, leave "Initialize with README" **unticked** so the push lands cleanly).

---

## Step 2 — Deploy backend on Render (Blueprint)

> **First time, or re-deploying from scratch?** Postgres and Redis are
> created **manually in the Render dashboard** (free tier, 90-day
> Postgres expiry, 25 MB Redis). The Blueprint only provisions the web
> service. `CORS_ORIGINS` is pre-filled with the canonical dashboard
> URL; `DATABASE_URL` and `REDIS_URL` are declared with `sync: false`
> so the dashboard shows them blank and prompts you to fill them in.

1. **Provision the data services first** (one-time, free tier):
   - Render dashboard → **New → PostgreSQL** → name `aegisone-postgres`,
     region Oregon, plan Free, Postgres 16. Copy the **Internal Database URL**
     (looks like `postgresql://aegisone_user:…@dpg-…/aegisone`).
   - Render dashboard → **New → Redis** → name `aegisone-redis`, region
     Oregon, plan Free (25 MB). Copy the **Internal Redis URL** (looks
     like `redis://red-…:6379`).
2. **Apply the Blueprint**:
   - Render dashboard → **Blueprints** → **New Blueprint Instance**.
   - Paste the repo URL: `https://github.com/DevangShah7/aegisone`.
   - Render reads `render.yaml` at the repo root and offers the
     `aegisone-backend-devshah` web service.
   - Click **Apply**. Wait ~5–10 min for the first build.
3. **Wire the env vars** (Render dashboard → `aegisone-backend-devshah`
   → **Environment**). Two will be blank:
   - `DATABASE_URL` — take the Postgres **Internal** URL and rewrite the
     scheme to `postgresql+psycopg://` (the async driver requirement).
     Example:
     `postgresql+psycopg://aegisone_user:<pw>@dpg-…-a.oregon-postgres.render.com/aegisone`
   - `REDIS_URL` — paste the Redis Internal URL as-is.
   - `CORS_ORIGINS` is already pre-filled with the canonical dashboard
     URL. If you deploy the dashboard under a different hostname,
     update this value and redeploy (Manual Deploy → Clear build cache).
4. **Trigger a deploy** so the new env vars take effect: **Manual
   Deploy → Clear build cache & deploy**.
5. Once the backend service is **Live**, copy its URL — looks like:
   ```
   https://aegisone-backend-devshah.onrender.com
   ```

Verify with: `curl https://aegisone-backend-devshah.onrender.com/healthz` → should return `{"status":"ok"}`.

> **What if the dashboard shows a CORS error like
> `No Access-Control-Allow-Origin header is present on the requested resource`?**
> That's almost always because `CORS_ORIGINS` is empty or doesn't
> include the dashboard's origin. The backend boot check now refuses
> to start with an empty `CORS_ORIGINS` in production, so the simplest
> path is: edit `CORS_ORIGINS` in Render → Environment to include your
> dashboard URL, then Manual Deploy.

---

## Step 3 — Deploy dashboard on Vercel

1. Open https://vercel.com → **Add New → Project** → **Import** `DevangShah7/aegisone`.
2. Set **Root Directory** = `dashboard`.
3. **Environment Variables** → add:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://aegisone-backend-devshah.onrender.com`
4. Click **Deploy**. Wait ~1 min.
5. Copy the dashboard URL — looks like:
   ```
   https://aegisone-dashboard.vercel.app
   ```

Now go back to **Step 2** and fix `CORS_ORIGINS` if you deployed the dashboard under a different hostname. Redeploy via Render's "Manual Deploy → Clear build cache & deploy" if needed.

> **What if Vercel says `DEPLOYMENT_NOT_FOUND` for the dashboard URL?**
> That means the dashboard project was never (or no longer) deployed.
> Go to https://vercel.com → your team → **Add New → Project** → import
> the same repo, set **Root Directory** to `dashboard`, add the env var
> above, and Deploy.

---

## Step 4 — Keep Render awake (free-tier gotcha)

Render's free web service sleeps after 15 minutes of no requests. Without a keepalive, the dashboard will feel slow on first load.

1. Sign in to https://cron-job.org.
2. **Cronjobs → New Cronjob**.
3. URL: `https://aegisone-backend-devshah.onrender.com/healthz`
4. Schedule: every **5 minutes** (`*/5 * * * *`).
5. Save.

Now Render never sleeps. Heartbeats, commands, and dashboard loads all stay fast.

---

## Step 5 — Rebuild the APK against the new backend

The APK currently points at the dead Cloudflare tunnel URL. Rebuild:

```powershell
cd E:\Code\AegisOne\android-agent
$env:JAVA_HOME = 'C:\Users\DEVANG\jdk-17\jdk-17.0.0+8'
# Adjust path to wherever your JDK 17 actually lives if the above is wrong.
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
# The base URL is consumed as a Gradle property (-P), NOT a shell env var.
# Setting $env:AegisOneApiBaseUrl has no effect.
.\gradlew.bat :app:assembleDebug -PAegisOneApiBaseUrl='https://aegisone-backend-devshah.onrender.com' --console=plain
```

New APK at: `E:\Code\AegisOne\android-agent\app\build\outputs\apk\debug\app-debug.apk`

Install:
```powershell
adb install -r E:\Code\AegisOne\android-agent\app\build\outputs\apk\debug\app-debug.apk
```

---

## Final URLs (paste into the chat once live)

- Backend: `https://aegisone-backend-devshah.onrender.com` (verify `/healthz` → 200)
- Dashboard: `https://dashboard-kappa-six-97.vercel.app` (verify login loads)
- Canonical dashboard alias `https://aegisone-dashboard.vercel.app` is held
  by a separate Vercel SSO project from a previous attempt — use the
  `dashboard-kappa-six-97.vercel.app` URL above until that's cleaned up.

---

## Operational notes (free-tier quirks)

| Concern | Behavior | Mitigation |
|---|---|---|
| Backend cold start after 15 min idle | First request takes ~30–50 s | cron-job.org keepalive (Step 4) |
| Postgres expires after 90 days | DB is wiped | Re-run alembic migrations; back up user accounts first |
| Redis 25 MB limit | Session/queue use only — fine for AegisOne | Upgrade if you hit the cap |
| HeartbeatWorker / CommandPollWorker | These run on the **Android device** via WorkManager, not on the backend. Backend is stateless. | — |
| APK signature | Debug-build only. Play Store needs a release key. | Outside scope of this slice. |

---

Developed by **Devang Shah** · 2026.
