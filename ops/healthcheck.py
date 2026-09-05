"""Healthcheck — the alarm for the failure mode nobody notices.

A stale panel serves last week's answer perfectly; nothing looks broken. This
asserts `panel_week` is within 10 days of today and exits non-zero otherwise.
Wire to an external uptime monitor against /api/health. Test the alert by lying
about the date — an untested alarm is not an alarm.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

STALE_DAYS = 10


def check(base_url: str | None = None, today: dt.date | None = None) -> dict:
    base = base_url or os.getenv("BHAO_API_URL", "http://localhost:8000")
    today = today or dt.date.today()
    with urllib.request.urlopen(f"{base}/api/health", timeout=10) as r:
        body = json.loads(r.read())
    panel_week = body.get("panel_week")
    age = (today - dt.date.fromisoformat(panel_week)).days if panel_week else None
    ok = body.get("status") == "ok" and age is not None and age <= STALE_DAYS
    return {
        "ok": ok,
        "status": body.get("status"),
        "panel_week": panel_week,
        "panel_age_days": age,
        "is_fixture": body.get("is_fixture"),
        "model_version": body.get("model_version"),
    }


def main() -> int:
    try:
        result = check()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps(result))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
