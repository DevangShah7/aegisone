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

1. Open https://dashboard.render.com → **Blueprints** → **New Blueprint Instance**.
2. Paste the repo URL: `https://github.com/DevangShah7/aegisone`.
3. Render reads `render.yaml` at the repo root and offers:
   - `aegisone-postgres` (free Postgres, 90-day expiry)
   - `aegisone-redis` (free Redis, 25 MB)
   - `aegisone-backend` (free web service)
4. Click **Apply**. Wait ~5–10 min for the first build.
5. Once the backend service is "Live", copy its URL — looks like:
   ```
   https://aegisone-backend.onrender.com
   ```
6. **Open the backend service → Environment tab → set `CORS_ORIGINS`** to your future Vercel URL (replace later if you don't have it yet — placeholder is fine for now):
   ```
   CORS_ORIGINS=https://aegisone-dashboard.vercel.app
   ```

Verify with: `curl https://aegisone-backend.onrender.com/healthz` → should return `{"status":"ok"}`.

---

## Step 3 — Deploy dashboard on Vercel

1. Open https://vercel.com → **Add New → Project** → **Import** `DevangShah7/aegisone`.
2. Set **Root Directory** = `dashboard`.
3. **Environment Variables** → add:
   - `NEXT_PUBLIC_API_BASE_URL` = `https://aegisone-backend.onrender.com`
4. Click **Deploy**. Wait ~1 min.
5. Copy the dashboard URL — looks like:
   ```
   https://aegisone-dashboard.vercel.app
   ```

Now go back to **Step 2** and fix `CORS_ORIGINS` if you used a placeholder. Redeploy via Render's "Manual Deploy → Clear build cache & deploy" if needed.

---

## Step 4 — Keep Render awake (free-tier gotcha)

Render's free web service sleeps after 15 minutes of no requests. Without a keepalive, the dashboard will feel slow on first load.

1. Sign in to https://cron-job.org.
2. **Cronjobs → New Cronjob**.
3. URL: `https://aegisone-backend.onrender.com/healthz`
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
$env:AegisOneApiBaseUrl = 'https://aegisone-backend.onrender.com'
.\gradlew.bat :app:assembleDebug --console=plain
```

New APK at: `E:\Code\AegisOne\android-agent\app\build\outputs\apk\debug\app-debug.apk`

Install:
```powershell
adb install -r E:\Code\AegisOne\android-agent\app\build\outputs\apk\debug\app-debug.apk
```

---

## Final URLs (paste into the chat once live)

- Backend: `https://aegisone-backend.onrender.com` (verify `/healthz` → 200)
- Dashboard: `https://aegisone-dashboard.vercel.app` (verify login loads)

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
