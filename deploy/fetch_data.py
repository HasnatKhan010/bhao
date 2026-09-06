"""Fetch the latest API artefacts from the GitHub Release at container start.

Runs BEFORE uvicorn on every cold start (HF Spaces / Render free tiers have
ephemeral disks), so a deployed API always serves the newest weekly panel
without anyone touching the server. Existing files are skipped so a warm
restart is instant; delete /app/data to force a refetch.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path

BASE = "https://github.com/HasnatKhan010/bhao/releases/latest/download"
DATA = Path(__import__("os").getenv("BHAO_DATA_DIR", "data"))

FILES = {
    "panel/prices_weekly.parquet": "prices_weekly.parquet",
    "panel/national_weekly.parquet": "national_weekly.parquet",
    "panel/items.parquet": "items.parquet",
    "panel/cities.parquet": "cities.parquet",
    "forecasts/forecasts.parquet": "forecasts.parquet",
    "forecasts/metrics.parquet": "metrics.parquet",
    "forecasts/drift.parquet": "drift.parquet",
    "registry/model_registry.json": "model_registry.json",
}


def main() -> None:
    for attempt in range(3):
        try:
            for rel, name in FILES.items():
                dest = DATA / rel
                if dest.exists():
                    print(f"  skip {rel} (exists)", flush=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                url = f"{BASE}/{name}"
                print(f"  fetch {url}", flush=True)
                urllib.request.urlretrieve(url, dest)
                print(f"  ok {rel}", flush=True)
            print("artefacts ready", flush=True)
            return
        except Exception as e:  # noqa: BLE001 — a release may be mid-update; retry
            print(f"  attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(5 * (attempt + 1))
    # last resort: start degraded — /api/health reports it, the site stays up
    print("WARNING: starting with incomplete artefacts", flush=True)


if __name__ == "__main__":
    main()
