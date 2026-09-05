"""API configuration and the DuckDB data layer.

Rule (07-TRACK-C-SERVE.md): **the API never imports from models/, features/ or
ingest/.** It reads parquet through DuckDB and nothing else. That isolation is why
a broken training run cannot take the site down.

One env var decides the data source:
    BHAO_DATA_DIR=contracts/fixtures   (default — fixture mode, banner ON)
    BHAO_DATA_DIR=data                 (real panel, banner OFF)
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTED_AT = time.time()

CACHE_TTL_SECONDS = int(os.getenv("BHAO_CACHE_TTL_SECONDS", "3600"))
RATE_LIMIT_JSON = int(os.getenv("BHAO_RATE_LIMIT_JSON", "60"))  # req/min/IP
RATE_LIMIT_CSV = int(os.getenv("BHAO_RATE_LIMIT_CSV", "5"))  # req/min/IP
DATASET_RELEASE_URL = os.getenv(
    "BHAO_DATASET_URL",
    "https://github.com/hasnatkhan010/bhao/releases/latest/download/panel.parquet",
)


def data_dir() -> Path:
    raw = os.getenv("BHAO_DATA_DIR", "contracts/fixtures")
    p = Path(raw)
    return p if p.is_absolute() else (REPO_ROOT / p)


@dataclass(frozen=True)
class Table:
    name: str
    subdir: str = ""


# name -> where it may live, in priority order. Panel tables sit under data/panel/
# in real mode and flat in contracts/fixtures/.
TABLE_LOCATIONS: dict[str, tuple[str, ...]] = {
    "prices_weekly": ("panel/prices_weekly.parquet", "prices_weekly.parquet"),
    "items": ("panel/items.parquet", "items.parquet"),
    "cities": ("panel/cities.parquet", "cities.parquet"),
    "national_weekly": ("panel/national_weekly.parquet", "national_weekly.parquet"),
    "wfp_monthly": ("panel/wfp_monthly.parquet", "wfp_monthly.parquet"),
    "forecasts": ("forecasts/forecasts.parquet", "forecasts.parquet"),
    "metrics": ("forecasts/metrics.parquet", "metrics.parquet"),
    "drift": ("forecasts/drift.parquet", "drift.parquet"),
}

REGISTRY_LOCATIONS = ("registry/model_registry.json", "model_registry.json")
MANIFEST_LOCATIONS = ("panel/_manifest.json", "_manifest.json")


def resolve(table: str) -> Path | None:
    base = data_dir()
    for rel in TABLE_LOCATIONS[table]:
        p = base / rel
        if p.exists():
            return p
    return None


def resolve_json(candidates: tuple[str, ...]) -> Path | None:
    base = data_dir()
    for rel in candidates:
        p = base / rel
        if p.exists():
            return p
    return None


class Store:
    """A read-only DuckDB connection over the parquet files, with a small TTL cache
    for the values every response's `meta` needs."""

    def __init__(self) -> None:
        self._con = duckdb.connect(database=":memory:", read_only=False)
        self._con.execute("SET threads=2")
        self._lock = threading.Lock()
        self._meta_cache: tuple[float, dict] | None = None

    # --- querying -----------------------------------------------------------

    def table_path(self, table: str) -> Path:
        p = resolve(table)
        if p is None:
            raise FileNotFoundError(
                f"{table}.parquet not found under {data_dir()} — "
                f"set BHAO_DATA_DIR or run `make fixtures`"
            )
        return p

    def has(self, table: str) -> bool:
        return resolve(table) is not None

    def sql(self, query: str, params: list | None = None):
        """Run a query. `{table}` placeholders are replaced with parquet scans."""
        with self._lock:
            return self._con.execute(query, params or []).fetchall()

    def df(self, query: str, params: list | None = None):
        with self._lock:
            return self._con.execute(query, params or []).df()

    def scan(self, table: str) -> str:
        """A parquet_scan expression for `table`, safe to inline into SQL."""
        path = str(self.table_path(table)).replace("\\", "/")
        return f"read_parquet('{path}')"

    # --- meta ---------------------------------------------------------------

    def registry(self) -> dict:
        p = resolve_json(REGISTRY_LOCATIONS)
        if p is None:
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def manifest(self) -> dict:
        p = resolve_json(MANIFEST_LOCATIONS)
        if p is None:
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def is_fixture(self) -> bool:
        """True when serving fixtures. Drives the app's banner — the guard that stops
        invented prices ending up in a portfolio screenshot."""
        reg = self.registry()
        if reg.get("meta", {}).get("is_fixture") is True:
            return True
        return data_dir().name == "fixtures"

    def meta(self) -> dict:
        now = time.time()
        if self._meta_cache and now - self._meta_cache[0] < 30:
            return self._meta_cache[1]
        panel_week = None
        rows = None
        if self.has("prices_weekly"):
            got = self.sql(
                f"SELECT max(week_ending)::VARCHAR, count(*) FROM {self.scan('prices_weekly')}"
            )
            if got:
                panel_week, rows = got[0][0], int(got[0][1])
        man = self.manifest()
        panel_week = panel_week or man.get("panel_week")
        reg = self.registry()
        forecast_run = None
        if self.has("forecasts"):
            got = self.sql(f"SELECT max(run_id) FROM {self.scan('forecasts')}")
            forecast_run = got[0][0] if got else None
        meta = {
            "panel_week": panel_week,
            "rows": rows if rows is not None else man.get("n_rows"),
            "model_version": reg.get("champion"),
            "forecast_run_id": forecast_run,
            "is_fixture": self.is_fixture(),
        }
        self._meta_cache = (now, meta)
        return meta

    def invalidate(self) -> None:
        self._meta_cache = None


_store: Store | None = None
_store_dir: Path | None = None


def store() -> Store:
    """Process-wide store; rebuilt if BHAO_DATA_DIR changes (tests flip it)."""
    global _store, _store_dir
    current = data_dir()
    if _store is None or _store_dir != current:
        _store = Store()
        _store_dir = current
    return _store


def uptime_s() -> int:
    return int(time.time() - STARTED_AT)
