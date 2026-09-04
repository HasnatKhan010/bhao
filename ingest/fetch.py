"""Content-addressed polite fetcher.

- 1 request per 2 s via a token bucket, a real UA naming the project (04-DATA-SOURCES.md).
- Cache: data/raw/{sha256[:2]}/{sha256}{ext} + a manifest row. **A re-run downloads nothing.**
- Retries: 3, exponential from 2 s, only on 5xx/429/timeout. A 404 is information — never retried.
- Wayback: same cache, `id_` suffix mandatory (raw bytes, not the HTML wrapper),
  backoff from 5 s, max 6 retries.
"""

from __future__ import annotations

import csv
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

from ingest import config
from ingest.ratelimit import TokenBucket

_bucket = TokenBucket(config.RATE_LIMIT_SECONDS)
_wayback_bucket = TokenBucket(max(config.WAYBACK_BACKOFF_BASE, config.RATE_LIMIT_SECONDS))

RETRYABLE = {429, 500, 502, 503, 504}


@dataclass
class Fetched:
    url: str
    sha256: str
    path: Path
    bytes: int
    from_cache: bool
    status: int


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cache_path(sha: str, ext: str) -> Path:
    return config.RAW_DIR / sha[:2] / f"{sha}{ext}"


def _manifest() -> Path:
    return config.RAW_DIR / "manifest.csv"


def _manifest_rows() -> list[dict]:
    if not _manifest().exists():
        return []
    with _manifest().open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _manifest_append(url: str, sha: str, nbytes: int, status: int) -> None:
    exists = _manifest().exists()
    with _manifest().open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["url", "sha256", "bytes", "status", "fetched_at"])
        w.writerow([url, sha, nbytes, status, _now()])


def _cache_lookup(url: str) -> Fetched | None:
    for row in _manifest_rows():
        if row["url"] != url:
            continue
        sha = row["sha256"]
        for p in (config.RAW_DIR / sha[:2]).glob(f"{sha}.*"):
            return Fetched(url, sha, p, int(row["bytes"]), True, int(row["status"]))
    return None


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    by_ct = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xlsx",
        "application/pdf": ".pdf",
        "text/html": ".html",
        "text/xml": ".xml",
        "application/xml": ".xml",
        "application/json": ".json",
        "text/csv": ".csv",
    }
    if ct in by_ct:
        return by_ct[ct]
    tail = url.split("?")[0].rsplit(".", 1)
    if len(tail) == 2 and 1 <= len(tail[1]) <= 5:
        return f".{tail[1].lower()}"
    return ".bin"


def _log_failure(url: str, status: int) -> None:
    log = config.RAW_DIR / "fetch_failures.csv"
    exists = log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["url", "status", "at"])
        w.writerow([url, status, _now()])


def _store(url: str, resp: requests.Response) -> Fetched:
    body = resp.content
    sha = hashlib.sha256(body).hexdigest()
    ext = _ext_for(resp.headers.get("Content-Type", ""), url)
    path = _cache_path(sha, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(body)
    if not any(r["sha256"] == sha for r in _manifest_rows()):
        _manifest_append(url, sha, len(body), resp.status_code)
    return Fetched(url, sha, path, len(body), False, resp.status_code)


def _get_with_retries(
    s: requests.Session, url: str, bucket: TokenBucket, max_retries: int, base_backoff: float, timeout: int
) -> requests.Response | None:
    """GET with exponential backoff on 5xx/429/timeout. Returns None on final 404.
    A 404 is never retried — it is information (the prefix table)."""
    attempt = 0
    while True:
        bucket.acquire()
        try:
            resp = s.get(url, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError):
            attempt += 1
            if attempt > max_retries:
                raise
            time.sleep(base_backoff * (2 ** (attempt - 1)))
            continue
        if resp.status_code == 404:
            _log_failure(url, 404)
            return None
        if resp.status_code in RETRYABLE:
            attempt += 1
            if attempt > max_retries:
                resp.raise_for_status()
            time.sleep(base_backoff * (2 ** (attempt - 1)))
            continue
        resp.raise_for_status()
        return resp


def fetch(url: str, session: requests.Session | None = None, force: bool = False) -> Fetched | None:
    """GET a URL politely, into the content-addressed cache. None on 404."""
    if not force:
        hit = _cache_lookup(url)
        if hit:
            return hit
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    resp = _get_with_retries(s, url, _bucket, 3, 2.0, 60)
    if resp is None:
        return None
    return _store(url, resp)


def fetch_wayback(
    original_url: str, timestamp: str, session: requests.Session | None = None
) -> Fetched | None:
    """Fetch raw original bytes from the Wayback Machine (`id_` suffix, mandatory)."""
    url = f"https://web.archive.org/web/{timestamp}id_/{quote(original_url, safe='/:')}"
    if hit := _cache_lookup(url):
        return hit
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", config.USER_AGENT)
    resp = _get_with_retries(
        s, url, _wayback_bucket, config.WAYBACK_MAX_RETRIES, config.WAYBACK_BACKOFF_BASE, 120
    )
    if resp is None:
        return None
    return _store(url, resp)


def cdx_query(url_pattern: str, extra: str = "collapse=urlkey&limit=5000") -> list[dict]:
    """Run a Wayback CDX query and return parsed rows."""
    base = (
        f"http://web.archive.org/cdx/search/cdx?url={quote(url_pattern, safe='*')}"
        f"&output=json&{extra}"
    )
    _wayback_bucket.acquire()
    resp = requests.get(base, headers={"User-Agent": config.USER_AGENT}, timeout=120)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return []
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:]]


def manifest_stats() -> dict:
    rows = _manifest_rows()
    return {"rows": len(rows), "bytes": sum(int(r["bytes"]) for r in rows)}
