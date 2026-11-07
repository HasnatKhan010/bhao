"""Fetch the latest API artefacts from the GitHub Release at container start.

Runs BEFORE uvicorn on every cold start (HF Spaces / Render free tiers have
ephemeral disks), so a deployed API always serves the newest weekly panel
without anyone touching the server. Existing files are skipped so a warm
restart is instant; delete /app/data to force a refetch.
"""

from __future__ import annotations

import argparse
import os
import time
import urllib.request
from pathlib import Path

BASE = "https://github.com/HasnatKhan010/bhao/releases/latest/download"
DATA = Path(os.getenv("BHAO_DATA_DIR", "data"))

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


def refresh() -> None:
    for rel, name in FILES.items():
        dest = DATA / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{BASE}/{name}"
        tmp = dest.with_suffix(dest.suffix + ".download")
        try:
            urllib.request.urlretrieve(url, tmp)
            if not dest.exists() or tmp.read_bytes() != dest.read_bytes():
                os.replace(tmp, dest)
                print(f"updated {rel}", flush=True)
        finally:
            tmp.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    while True:
        try:
            refresh()
        except Exception as e:  # noqa: BLE001 — retain the last complete download
            print(f"data refresh failed: {e}", flush=True)
        if not args.watch:
            return
        time.sleep(3600)


if __name__ == "__main__":
    main()
