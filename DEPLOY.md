# Deploying Bhao — free, no credit card

Three pieces, all free tiers, ~15 minutes of clicking:

| Piece | Host | Free tier | Notes |
|---|---|---|---|
| **API** (FastAPI + parquet) | **Render** (Docker, free instance) | ✅ no card; spins down after 15 min idle, ~1 min cold start | fetches the latest artefacts from the GitHub Release at every boot |
| **Web** (Next.js) | Vercel Hobby | ✅ no card; no cold-start problem | two env vars in the dashboard |
| **Keep-alive + staleness alarm** | UptimeRobot (free) | ✅ | pings `/api/health` every 10 min so the API never sleeps and a stale panel alerts you |

> Note: Hugging Face **Docker** Spaces moved behind their paid PRO plan (verified
> on the Space-creation screen), so the free path is Render. The dataset itself
> lives on **GitHub Releases** (publishes weekly, automatic) — permanent, free,
> and independent of any host.

---

## 1. API — Render (~5 min)

1. Sign in at render.com with GitHub → **New + → Web Service**.
2. Pick the `HasnatKhan010/bhao` repo.
3. Settings:
   - **Runtime**: Docker (Render finds `docker/Dockerfile.api`? no — set
     **Dockerfile Path**: `docker/Dockerfile.api`)
   - **Instance Type**: Free
   - **Health Check Path**: `/api/health`
4. Deploy. On boot the container runs `fetch_data.py`, which pulls the latest
   panel, forecasts, metrics, drift and registry from the GitHub Release.
5. Your API: `https://bhao-api.onrender.com` → `/api/health` should say
   `status: ok` with a fresh `panel_week` (first boot takes ~1 min).

> Every Sunday the GitHub cron publishes a new release; the next cold boot
> (or the UptimeRobot ping, if the service had spun down) serves the new week
> automatically. No logins, no redeploys.

## 2. Web — Vercel (~5 min)

1. Import the repo at vercel.com → **New Project** → **Root Directory**: `web`.
2. Environment variables (Project → Settings → Environment Variables):
   - `NEXT_PUBLIC_BHAO_API_URL` = `https://bhao-api.onrender.com`
   - `BHAO_API_URL` = same value (the `/api/*` rewrites and Swagger iframe)
3. Deploy → `https://<project>.vercel.app`. Open the home page → real prices,
   fresh `Panel week`, forecast + error bar.

## 3. Keep-alive + alarm — UptimeRobot (~5 min)

1. Free monitor: **HTTP(s)** → `https://bhao-api.onrender.com/api/health` →
   every 10 min.
2. That ping keeps the Render service warm (no spin-down) and doubles as the
   staleness alarm: `/api/health` reports `status: degraded` when `panel_week`
   is older than 10 days — add a UptimeRobot **keyword alert** on `degraded`
   to your email.

## 4. Verify

- `https://<web>.vercel.app/` → pick a city + item → forecast + error bar.
- `https://<web>.vercel.app/en/scorecard` → live model table.
- `https://bhao-api.onrender.com/api/health` → `ok`, fresh `panel_week`.
- `https://github.com/HasnatKhan010/bhao/actions` → Sunday cron green; the
  release assets refresh and the deployed API picks them up.

## Costs

| Item | Cost |
|---|---|
| Render free instance (750 h/month) | $0 |
| Vercel Hobby | $0 |
| UptimeRobot (50 monitors) | $0 |
| GitHub Releases + Actions (public repo) | $0 |
| **Total** | **$0** |

## If you outgrow free

Render cold starts are the main annoyance (1 min on the first request after 15
idle minutes; the keep-alive ping makes that rare). Ladder (12-RISKS.md R8):
Render free → Fly.io (~$3/mo, always on) → any $4 VPS. The API is stateless,
reads parquet from disk, and moving hosts is a Dockerfile away. The dataset on
GitHub Releases survives any hosting outcome.
