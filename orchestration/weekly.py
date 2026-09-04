"""The weekly flow — idempotent: running it twice changes nothing.

    discover → fetch → parse → normalise → validate → publish → manifest

Failures raise loudly (the caller — GitHub Actions — opens an issue). A stale-but-
correct panel beats a fresh-but-wrong one, so validation failures never publish.
"""

from __future__ import annotations

import datetime as dt
import json
import sys

import pandas as pd

from ingest import config, validate as vld
from ingest.discover import download_report, find_report
from ingest.fetch import cdx_query
from ingest.normalise import resolve_item, urdu_labels
from ingest.parse_annex import ParsedAnnex, parse_annex
from ingest.parse_spi import ParsedSPI, parse_spi
from ingest.publish import (
    ItemResolver,
    annex_to_frame,
    append_week,
    load_panel,
    spi_to_frame,
    write_cities,
    write_items,
    write_national,
    write_panel,
)


def _national_prices_by_code(spi: ParsedSPI, resolver: ItemResolver) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in spi.rows:
        if r.is_headline or r.price_this_week is None:
            continue
        try:
            code, _ = resolver.resolve(r.item_raw, r.unit_raw)
        except KeyError:
            continue
        out.setdefault(code, r.price_this_week)
    return out


def _city_means_by_code(prices: pd.DataFrame) -> dict[str, float]:
    sub = prices[prices["price_avg"].notna()]
    return sub.groupby("item_code")["price_avg"].mean().to_dict()


def ingest_week(
    week_ending: dt.date, spi_path, annex_path, spi_url: str, annex_url: str,
    panel: pd.DataFrame | None = None, resolver: ItemResolver | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Parse + normalise + validate one week. Returns (new_panel, prices, national).

    Raises ValidationError on any business-rule failure — the caller must not publish.
    """
    resolver = resolver or ItemResolver()
    panel = panel if panel is not None else load_panel()

    annex: ParsedAnnex = parse_annex(annex_path)
    spi: ParsedSPI = parse_spi(spi_path)
    if annex.week_ending is None:
        annex.week_ending = week_ending
    if annex.week_ending != week_ending:
        raise vld.ValidationError(
            f"annex banner says week {annex.week_ending}, expected {week_ending}"
        )
    annex.source_url = annex_url

    prices = annex_to_frame(annex, resolver)
    national = spi_to_frame(spi, week_ending, spi_url, resolver)

    # the column-offset defence: national table vs unweighted mean of city avgs
    vld.national_crosscheck(
        _city_means_by_code(prices), _national_prices_by_code(spi, resolver)
    )
    # the full gate: schema + week gap + coverage + quarantine
    prices = vld.validate_prices(prices, panel, week_ending)

    new_panel, n_revs = append_week(panel, prices)
    return new_panel, prices, national, n_revs


def run(week_ending: dt.date | None = None) -> dict:
    """One weekly run. Idempotent by construction of append_week."""
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    config.ensure_dirs()

    if week_ending is None:
        refs = find_report_for_latest(session)
    else:
        refs = find_report(week_ending, session)
    if refs is None:
        raise RuntimeError(f"no SPI report discovered for week {week_ending or 'latest'}")
    week_ending = refs.week_ending

    paths = download_report(refs, session)
    if not paths["spi"] or not paths["annex"]:
        raise RuntimeError(f"missing downloads for week {week_ending}: {paths}")

    resolver = ItemResolver()
    panel = load_panel()
    new_panel, prices, national, n_revs = ingest_week(
        week_ending, paths["spi"], paths["annex"], refs.spi_url, refs.annex_url, panel, resolver
    )

    write_panel(new_panel)
    write_national(national)
    write_items(new_panel, resolver)
    write_cities()

    weeks = sorted(set(pd.to_datetime(new_panel["week_ending"]).dt.date))
    return {
        "week_ending": week_ending.isoformat(),
        "rows_this_week": int(len(prices)),
        "non_null_this_week": int(prices["price_avg"].notna().sum()),
        "new_revision_rows": n_revs,
        "panel_weeks": len(weeks),
        "panel_rows": int(len(new_panel)),
        "new_items": sorted(resolver.dynamic),
    }


def find_report_for_latest(session) -> "object":  # noqa: F821
    from ingest.discover import latest_week

    lw = latest_week(session)
    if lw is None:
        raise RuntimeError("sitemap gave no latest week; pass an explicit week_ending")
    return find_report(lw, session)


def backfill_all(session=None) -> dict:
    """One-off: walk every known week (sitemap + CDX), fetch, parse, publish.

    Writes data/raw/coverage_report.csv for every Thursday from the earliest found
    to now — obtained or not, and from where. Honest gaps, published.
    """
    import requests

    session = session or requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT
    config.ensure_dirs()

    from ingest.discover import all_known_weeks

    known = all_known_weeks(session)
    if not known:
        raise RuntimeError("no weeks discoverable at all")
    resolver = ItemResolver()
    panel = load_panel()

    coverage_rows = []
    today = dt.date.today()
    start = min(known)
    every_thursday = []
    d = start
    while d <= today:
        every_thursday.append(d)
        d += dt.timedelta(days=7)

    for week in every_thursday:
        status, src = "missing", ""
        if week in known or week >= max(known) - dt.timedelta(days=21):
            refs = find_report(week, session)
            if refs is not None:
                paths = download_report(refs, session)
                if paths["spi"] and paths["annex"]:
                    try:
                        panel, _, _, n_revs = ingest_week(
                            week, paths["spi"], paths["annex"],
                            refs.spi_url or "", refs.annex_url or "", panel, resolver,
                        )
                        status, src = "ok", refs.strategy or ""
                        write_panel(panel)
                    except vld.ValidationError as e:
                        status, src = f"invalid: {e}", refs.strategy or ""
                    except AssertionError as e:
                        status, src = f"parse_assert: {e}", refs.strategy or ""
                else:
                    status = "found_but_download_missing"
                if refs.post_url:
                    src = (src + " post:" + refs.post_url).strip()
        coverage_rows.append({
            "week_ending": week.isoformat(), "status": status, "source": src,
        })
        print(f"{week} {status[:60]}", flush=True)

    import csv as _csv

    with config.COVERAGE_REPORT.open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=["week_ending", "status", "source"])
        w.writeheader()
        w.writerows(coverage_rows)

    ok = sum(1 for r in coverage_rows if r["status"] == "ok")
    resolver.save()
    return {"weeks": len(every_thursday), "ok": ok, "missing": len(every_thursday) - ok}


if __name__ == "__main__":
    week = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    result = run(week)
    print(json.dumps(result, indent=2, ensure_ascii=False))
