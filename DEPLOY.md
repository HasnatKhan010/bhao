# Deploying Bhao — free, no credit card

Three pieces, all free tiers, ~20 minutes of clicking:

| Piece | Host | Free tier | Notes |
|---|---|---|---|
| **API** (FastAPI + parquet) | Hugging Face Spaces (Docker) | ✅ no card; sleeps after 48 h idle, wakes on request | artefacts self-fetch from the GitHub Release at every cold start |
| **Web** (Next.js) | Vercel Hobby | ✅ no card; no cold-start problem | set two env vars in the dashboard |
| **Keep-alive + staleness alarm** | UptimeRobot (free) | ✅ | pings `/api/health` every 10 min so the space never sleeps and a stale panel pages you |

The dataset itself lives on **GitHub Releases** (already publishing weekly) — permanent, free, independent of any host.

---

## 1. API — Hugging Face Space (~10 min)

1. Sign in at huggingface.co → **New → Space**.
2. Name: `bhao-api` · SDK: **Docker** · Visibility: **Public** · License: MIT.
3. Upload the three files from `deploy/api-space/`: `Dockerfile`, `README.md`
   (keep the yaml frontmatter — it configures the Space), `fetch_data.py`.
4. The Space builds (~3 min) and starts. On cold start it pulls the latest
   artefacts from the GitHub Release automatically.
5. Your API is now at `https://<your-username>-bhao-api.hf.space` — check
   `/api/health` shows `status: ok` and a fresh `panel_week`.

> The space fetches `panel.parquet, national_weekly, items, cities, forecasts,
> metrics, drift, model_registry.json` from the release. The weekly workflow
> uploads all of them every Sunday.

## 2. Web — Vercel (~5 min)

1. Push/import the repo at vercel.com → **New Project** → set **Root Directory**
   to `web`.
2. Environment variables (Project → Settings → Environment Variables):
   - `NEXT_PUBLIC_BHAO_API_URL` = `https://<your-username>-bhao-api.hf.space`
   - `BHAO_API_URL` = same value (used by the `/api/*` rewrites and the Swagger iframe)
3. Deploy. Vercel builds `web/` and serves it on
   `https://<project>.vercel.app`.
4. Open the site → the home card should show real prices with `Panel week` fresh.

## 3. Keep-alive + alarm — UptimeRobot (~5 min)

1. Create a free monitor: **HTTP(s)** →
   `https://<your-username>-bhao-api.hf.space/api/health` → every 10 min.
2. That ping keeps the Space awake (no 48 h sleep) and doubles as the
   staleness alarm: `/api/health` reports `status: degraded` when `panel_week`
   is older than 10 days — wire the UptimeRobot "keyword" alert on `"degraded"`
   to your email.

## 4. Verify

- `https://<web>.vercel.app/` → pick a city + item → real forecast + error bar.
- `https://<web>.vercel.app/en/scorecard` → live model table.
- `https://<api>.hf.space/api/health` → `ok`, fresh `panel_week`.
- `https://github.com/HasnatKhan010/bhao/actions` → the Sunday cron now also
  refreshes the deployed API by publishing the new release (the space fetches
  it on next cold start; the keep-alive ping forces a restart-free read of the
  same files).

## Costs

| Item | Cost |
|---|---|
| HF Space (CPU, 2 vCPU, 16 GB) | $0 |
| Vercel Hobby | $0 |
| UptimeRobot (50 monitors) | $0 |
| GitHub Releases + Actions (public repo) | $0 |
| **Total** | **$0** |

## If you outgrow free

The fallback ladder (12-RISKS.md R8): HF Space → Render free → Fly.io
(~$3/mo, no sleep) → any $4 VPS. The API is stateless and reads parquet from
disk; moving hosts is a Dockerfile away. The dataset on GitHub Releases survives
any hosting outcome.
