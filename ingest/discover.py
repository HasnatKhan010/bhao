"""Discovery — find this week's SPI file, tolerate renames (05-TRACK-A-INGEST.md).

Three strategies, in the order fixed by 04-DATA-SOURCES.md, and the winner is logged:

1. post-sitemap.xml filtered for `weekly-sensitive-price-indicator` (recent weeks only)
2. construct the post URL from the target Thursday and HEAD it
3. Wayback CDX for anything older

The filename convention has already changed at least once (`SPI-Report-` →
`3.-SPI-Report-`), so candidates are a LIST, never one hardcoded string. Every 404
and every success is logged to data/raw/discovery_log.csv.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from ingest import config
from ingest.fetch import cdx_query, fetch, fetch_wayback

POST_SLUG = "weekly-sensitive-price-indicator-spi-for-the-week-ended-on-{dd}-{mm}-{yyyy}"
SITEMAP_URL = f"{config.PBS_BASE}/post-sitemap.xml"
CDX_PATTERN = "pbs.gov.pk/wp-content/uploads*"

_SITEMAP_CACHE: tuple[float, list[str]] | None = None
_SITEMAP_TTL = 3600


@dataclass
class ReportRefs:
    week_ending: dt.date
    spi_url: str | None = None
    annex_url: str | None = None
    post_url: str | None = None
    wayback_timestamp: str | None = None
    strategy: str | None = None
    tried: list[str] = field(default_factory=list)


def _log_discovery(week: dt.date, strategy: str, url: str, status: str, tried: list[str]) -> None:
    log = config.DISCOVERY_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    exists = log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["week_ending", "strategy", "url", "status", "tried_urls", "at"])
        w.writerow([week.isoformat(), strategy, url, status, " | ".join(tried), _now()])


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _candidate_file_urls(prefixes: list[str], week: dt.date, ext: str) -> list[str]:
    """Every prefix × separator combination, in the documented order."""
    out = []
    for prefix in prefixes:
        for sep in config.SEPARATORS:
            fname = f"{prefix}{week.strftime(sep.join(['%d', '%m', '%Y']))}{ext}"
            out.append(f"{config.PBS_BASE}{config.UPLOAD_DIR}/{fname}")
    return out


def _sitemap_spi_posts(session: requests.Session) -> list[str]:
    global _SITEMAP_CACHE
    now = time.monotonic()
    if _SITEMAP_CACHE and now - _SITEMAP_CACHE[0] < _SITEMAP_TTL:
        return _SITEMAP_CACHE[1]
    resp = session.get(SITEMAP_URL, headers={"User-Agent": config.USER_AGENT}, timeout=30)
    resp.raise_for_status()
    urls = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    posts = [u for u in urls if "weekly-sensitive-price-indicator" in u]
    _SITEMAP_CACHE = (now, posts)
    return posts


def _attachment_urls_from_post(post_url: str, session: requests.Session) -> dict[str, str]:
    """Scrape a post page for .xlsx links (the robust fallback when the filename
    convention changed but the post exists)."""
    try:
        resp = session.get(post_url, headers={"User-Agent": config.USER_AGENT}, timeout=30)
    except requests.RequestException:
        return {}
    if resp.status_code != 200:
        return {}
    links = re.findall(r'href=["\']([^"\']+\.xlsx)["\']', resp.text, flags=re.I)
    out: dict[str, str] = {}
    for link in links:
        absolute = link if link.startswith("http") else f"{config.PBS_BASE}{link}"
        if "annex" in link.lower():
            out["annex"] = absolute
        elif "spi" in link.lower():
            out.setdefault("spi", absolute)
    return out


def _from_sitemap(week: dt.date, session: requests.Session, refs: ReportRefs) -> bool:
    posts = _sitemap_spi_posts(session)
    target = POST_SLUG.format(dd=f"{week.day:02d}", mm=f"{week.month:02d}", yyyy=week.year)
    match = next((p for p in posts if p.rstrip("/").endswith(target)), None)
    if not match:
        return False
    files = _attachment_urls_from_post(match, session)
    if not files:
        return False
    refs.post_url = match
    refs.spi_url = files.get("spi")
    refs.annex_url = files.get("annex")
    refs.strategy = "sitemap"
    return bool(refs.spi_url or refs.annex_url)


def _from_constructed_url(week: dt.date, session: requests.Session, refs: ReportRefs) -> bool:
    slug = POST_SLUG.format(dd=f"{week.day:02d}", mm=f"{week.month:02d}", yyyy=week.year)
    post_url = f"{config.PBS_BASE}/{slug}/"
    refs.tried.append(post_url)
    try:
        resp = session.head(
            post_url, headers={"User-Agent": config.USER_AGENT}, timeout=20, allow_redirects=True
        )
    except requests.RequestException:
        return False
    if resp.status_code != 200:
        return False
    refs.post_url = post_url
    # try the candidate list for direct file URLs; if none hit, scrape the post page
    for kind, prefixes in (("spi", config.SPI_PREFIXES), ("annex", config.ANNEX_PREFIXES)):
        for url in _candidate_file_urls(prefixes, week, ".xlsx"):
            refs.tried.append(url)
            try:
                head = session.head(
                    url, headers={"User-Agent": config.USER_AGENT}, timeout=20, allow_redirects=True
                )
            except requests.RequestException:
                continue
            if head.status_code == 200:
                if kind == "spi":
                    refs.spi_url = url
                else:
                    refs.annex_url = url
                refs.strategy = refs.strategy or "constructed_url"
    if not (refs.spi_url or refs.annex_url):
        files = _attachment_urls_from_post(post_url, session)
        refs.spi_url = files.get("spi")
        refs.annex_url = files.get("annex")
        refs.strategy = "constructed_post_scrape"
    return bool(refs.spi_url or refs.annex_url)


def cdx_file_map(session: requests.Session | None = None) -> dict[dt.date, list[tuple[str, str]]]:
    """One CDX pass over the uploads folder → {week_ending_Thursday: [(ts, url), ...]}.

    The xlsx files ARE in the archive (1,568 captures verified); the post pages are
    not a reliable index for them. Build the map once per backfill run instead of
    querying CDX per week.
    """
    out: dict[dt.date, list[tuple[str, str]]] = {}
    for row in cdx_query(
        "pbs.gov.pk/wp-content/uploads*",
        extra="collapse=urlkey&limit=10000&filter=original:.*\\.xlsx.*",
    ):
        original = row.get("original", "")
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", original)
        if not m:
            continue
        try:
            d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        if d.weekday() != 3:  # Thursday
            continue
        out.setdefault(d, []).append((row["timestamp"], original))
    for v in out.values():
        v.sort()
    return out


def _from_cdx(
    week: dt.date, refs: ReportRefs, cdx_map: dict[dt.date, list[tuple[str, str]]] | None = None
) -> bool:
    entries = cdx_map.get(week) if cdx_map is not None else None
    if entries is None:
        rows = cdx_query(
            CDX_PATTERN, extra="collapse=urlkey&limit=5000&filter=original:.*[Aa]nnex.*"
        )
        stamp = week.strftime("%d.%m.%Y")
        entries = [(r["timestamp"], r["original"]) for r in rows if stamp in r.get("original", "")]
    annex = next(((t, u) for t, u in entries if "annex" in u.lower()), None)
    spi = next(
        ((t, u) for t, u in entries if "spi" in u.lower() and "annex" not in u.lower()), None
    )
    if annex:
        refs.wayback_timestamp, refs.annex_url = annex
        refs.strategy = "wayback_cdx"
    if spi:
        if refs.annex_url is None:
            refs.wayback_timestamp, refs.annex_url = spi  # fallback: treat as the file
        else:
            refs.spi_url = spi[1]
        refs.strategy = refs.strategy or "wayback_cdx"
    return bool(refs.annex_url or refs.spi_url)


def find_report(
    week: dt.date,
    session: requests.Session | None = None,
    cdx_map: dict[dt.date, list[tuple[str, str]]] | None = None,
) -> ReportRefs | None:
    """Find the SPI report + annex for the week ending `week`. None if not found."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    refs = ReportRefs(week_ending=week)
    for strategy in (_from_sitemap, _from_constructed_url):
        try:
            if strategy(week, s, refs):
                _log_discovery(
                    week, refs.strategy, refs.spi_url or refs.annex_url or "", "found", refs.tried
                )
                return refs
        except requests.RequestException:
            continue
    try:
        if _from_cdx(week, refs, cdx_map):
            _log_discovery(
                week, refs.strategy, refs.annex_url or refs.spi_url or "", "found", refs.tried
            )
            return refs
    except requests.RequestException:
        pass
    _log_discovery(week, "none", "", "not_found", refs.tried)
    return None


def latest_week(session: requests.Session | None = None) -> dt.date | None:
    """The most recent SPI week visible on the live site (sitemap strategy)."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    try:
        posts = _sitemap_spi_posts(s)
    except requests.RequestException:
        return None
    pat = re.compile(r"week-ended-on-(\d{2})-(\d{2})-(\d{4})")
    best: dt.date | None = None
    for p in posts:
        m = pat.search(p)
        if not m:
            continue
        d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if best is None or d > best:
            best = d
    return best


def all_known_weeks(session: requests.Session | None = None) -> list[dt.date]:
    """Sitemap + CDX, deduped. The honest list of what exists to be fetched."""
    weeks: set[dt.date] = set()
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    pat = re.compile(r"week-ended-on-(\d{2})-(\d{2})-(\d{4})")
    try:
        for p in _sitemap_spi_posts(s):
            m = pat.search(p)
            if m:
                weeks.add(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    except requests.RequestException:
        pass
    try:
        for row in cdx_query(
            "pbs.gov.pk/weekly-sensitive-price-indicator*", extra="collapse=urlkey&limit=5000"
        ):
            m = pat.search(row.get("original", ""))
            if m:
                weeks.add(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    except requests.RequestException:
        pass
    return sorted(weeks)


def download_report(
    refs: ReportRefs, session: requests.Session | None = None
) -> dict[str, Path | None]:
    """Fetch the report + annex into the cache; returns local paths."""
    out: dict[str, Path | None] = {"spi": None, "annex": None}
    if refs.spi_url:
        if refs.wayback_timestamp:
            got = fetch_wayback(refs.spi_url, refs.wayback_timestamp, session)
        else:
            got = fetch(refs.spi_url, session)
        out["spi"] = got.path if got else None
    if refs.annex_url:
        if refs.wayback_timestamp:
            got = fetch_wayback(refs.annex_url, refs.wayback_timestamp, session)
        else:
            got = fetch(refs.annex_url, session)
        out["annex"] = got.path if got else None
    return out
