"""Ingest configuration — paths, politeness, UA. A owns this."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("BHAO_DATA_DIR", str(REPO_ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
PANEL_DIR = DATA_DIR / "panel"
FORECASTS_DIR = DATA_DIR / "forecasts"
REGISTRY_DIR = DATA_DIR / "registry"

# `data/` and `contracts/fixtures/` are both legitimate panel roots; the fixture
# generator and tests use a local out dir. Consumers resolve via BHAO_DATA_DIR.

PBS_BASE = "https://www.pbs.gov.pk"

# UA per 04-DATA-SOURCES.md: name the project, give a contact URL.
USER_AGENT = os.getenv(
    "BHAO_USER_AGENT",
    "bhao/0.1 (+https://github.com/hasnatkhan010/bhao) weekly-price-research",
)

RATE_LIMIT_SECONDS = float(os.getenv("BHAO_RATE_LIMIT_SECONDS", "2"))
WAYBACK_BACKOFF_BASE = float(os.getenv("BHAO_WAYBACK_BACKOFF_BASE", "5"))
WAYBACK_MAX_RETRIES = int(os.getenv("BHAO_WAYBACK_MAX_RETRIES", "6"))

# Filename conventions that have been observed (04-DATA-SOURCES.md §TRAP).
SPI_PREFIXES = ["SPI-Report-", "3.-SPI-Report-", "2.-SPI-Report-", "SPI_Report_", "SPI-Report_"]
ANNEX_PREFIXES = ["Annex-", "Annex_", "3.-Annex-", "2.-Annex-", "1.-Annex-"]
SEPARATORS = [".", "-", "_"]
# WordPress quirk: attachments live under a FIXED uploads folder, not the real date.
UPLOAD_DIR = "/wp-content/uploads/2020/07/"

MANIFEST_PATH = PANEL_DIR / "_manifest.json"
DISCOVERY_LOG = RAW_DIR / "discovery_log.csv"
COVERAGE_REPORT = RAW_DIR / "coverage_report.csv"
QUARANTINE_LOG = RAW_DIR / "quarantine.csv"

PUBLICATION_LAG_DAYS = 2  # PBS publishes the Friday after the Thursday surveyed


def ensure_dirs() -> None:
    for d in (RAW_DIR, PANEL_DIR, FORECASTS_DIR, REGISTRY_DIR):
        d.mkdir(parents=True, exist_ok=True)
