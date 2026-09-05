"""Validation — Pandera schema + business rules. Exit non-zero on failure; nothing
reaches data/panel/ unless it passes (05-TRACK-A-INGEST.md).

Business rules beyond the schema:
- week gap: this week_ending is exactly 7 days after the previous published week
- coverage: non-null count within 20% of last week's (a collapse = parse break)
- price sanity: no price_avg >5x or <0.2x the series' 8-week median → quarantine
- national cross-check: per item, unweighted mean of city AVGs within 30% of the
  national price. **The assertion that catches a column-offset bug.**
"""

from __future__ import annotations

import csv
import datetime as dt

import numpy as np
import pandas as pd

from contracts.schemas import SCHEMAS, validate_frame
from ingest import config


class ValidationError(RuntimeError):
    pass


def check_week_gap(new_week: dt.date, panel: pd.DataFrame, skip: bool = False) -> None:
    if skip:
        return
    if panel.empty or "week_ending" not in panel.columns:
        return
    weeks = sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))
    if not weeks:
        return
    prev = weeks[-1]
    if new_week < prev:
        raise ValidationError(f"week {new_week} is before the latest published week {prev}")
    if new_week == prev:
        return  # re-ingest of the current week: append_week makes it a no-op
    if (new_week - prev).days != 7:
        raise ValidationError(f"week gap: {new_week} is {(new_week - prev).days} days after {prev}, expected 7")


def check_coverage(new_prices: pd.DataFrame, panel: pd.DataFrame, tolerance: float = 0.20) -> None:
    """Non-null count of the new week within ±20% of the previous week's."""
    if panel.empty or "week_ending" not in panel.columns:
        return
    weeks = sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))
    if not weeks:
        return
    prev_week = weeks[-1]
    prev_n = int(panel[pd.to_datetime(panel["week_ending"]).dt.date == prev_week]["price_avg"].notna().sum())
    new_n = int(new_prices["price_avg"].notna().sum())
    if prev_n == 0:
        return
    if abs(new_n - prev_n) / prev_n > tolerance:
        raise ValidationError(
            f"coverage collapse: new week has {new_n} non-null prices vs {prev_n} last week "
            f"({new_n / prev_n:.0%}) — a parse break, not a survey change"
        )


def quarantine_sanity(new_prices: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Rows whose price_avg is >5x or <0.2x the series' trailing 8-week median.

    Returns the clean frame; quarantined rows go to data/raw/quarantine.csv and are
    held out of the panel until a human looks.
    """
    if panel.empty:
        return new_prices
    hist = panel[panel["revision"] == 0]
    medians = (
        hist.sort_values("week_ending")
        .groupby(["city_code", "item_code"])
        .tail(8)
        .groupby(["city_code", "item_code"])["price_avg"]
        .median()
        .rename("median8")
    )
    joined = new_prices.merge(
        medians, left_on=["city_code", "item_code"], right_index=True, how="left"
    )
    med = joined["median8"]
    bad = (
        med.notna()
        & joined["price_avg"].notna()
        & ((joined["price_avg"] > 5 * med) | (joined["price_avg"] < 0.2 * med))
    )
    if bad.any():
        q = joined[bad].copy()
        q["quarantined_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        q["reason"] = "price outside [0.2x, 5x] of trailing 8-week median"
        log = config.QUARANTINE_LOG
        log.parent.mkdir(parents=True, exist_ok=True)
        q.to_csv(log, mode="a", header=not log.exists(), index=False)
        joined = joined[~bad]
    return joined.drop(columns=["median8"], errors="ignore")


def national_crosscheck(
    city_mean_by_item: dict[str, float], national_by_item: dict[str, float], tolerance: float = 0.30
) -> None:
    """Per item: unweighted mean of the 17 city AVGs vs the national price_this_week.

    Not equal — PBS weights — but a 30% gap means the parse is misaligned: onion
    prices have landed in the tomato row and nothing crashed. This check is the only
    defence; it runs on resolved item codes.
    """
    violations = []
    for code, nat in national_by_item.items():
        cm = city_mean_by_item.get(code)
        if cm is None or nat is None or nat == 0:
            continue
        gap = abs(cm - nat) / nat
        if gap > tolerance:
            violations.append(f"item {code}: city-mean {cm:.2f} vs national {nat:.2f} (gap {gap:.0%})")
    if violations:
        raise ValidationError(
            "national-vs-city cross-check FAILED — a column is probably misaligned:\n"
            + "\n".join(violations[:20])
        )


def validate_prices(new_prices: pd.DataFrame, panel: pd.DataFrame, new_week: dt.date,
                    skip_gap: bool = False) -> pd.DataFrame:
    """Full gate: schema, then business rules. Raises ValidationError on any failure."""
    validate_frame(new_prices, "prices_weekly")
    check_week_gap(new_week, panel, skip=skip_gap)
    check_coverage(new_prices, panel)
    return quarantine_sanity(new_prices, panel)
