"""Precompute the Hijri calendar table — Ramadan/Eid flags per week_ending.

Ramadan moves ~11 days earlier each solar year, so week-of-year cannot capture it,
and food prices in Pakistan are not stationary across Ramadan (06-TRACK-B-MODEL.md).
Written once to features/hijri_weeks.csv; committed so folds are reproducible.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from hijridate import Gregorian, Hijri
from hijridate import convert as _conv

HERE = Path(__file__).parent
OUT = HERE / "hijri_weeks.csv"

RAMADAN_MONTH = 9
SHAWWAL_MONTH = 10
# Eid al-Fitr = 1 Shawwal; Eid al-Adha = 10 Dhul-Hijjah (month 12)
EID_AL_ADHA_DAY = 10
DHUL_HIJJAH = 12


def hijri_flags_for_week(week_ending: dt.date) -> dict[str, int | float]:
    """Flags for the week ending Thursday: is any day of the (week-6..week) window
    in Ramadan / an Eid? Shopping patterns run through the whole month, so the
    window is the week itself plus the preceding two weeks."""
    flags = {"ramadan": 0, "eid_fitr": 0, "eid_adha": 0, "hijri_month": 0.0}
    for offset in range(0, 21, 7):  # week, week-1, week-2
        d = week_ending - dt.timedelta(days=offset)
        try:
            h = Gregorian(d.year, d.month, d.day).to_hijri()
        except (ValueError, OverflowError):
            continue
        flags["hijri_month"] = h.month
        if h.month == RAMADAN_MONTH:
            flags["ramadan"] = 1
        if h.month == SHAWWAL_MONTH and h.day <= 7:
            flags["eid_fitr"] = 1
        if h.month == DHUL_HIJJAH and EID_AL_ADHA_DAY - 3 <= h.day <= EID_AL_ADHA_DAY + 3:
            flags["eid_adha"] = 1
    return flags


def main() -> None:
    import pandas as pd

    start = dt.date(2020, 1, 2)
    end = dt.date(2030, 12, 31)
    rows = []
    d = start
    while d <= end:
        flags = hijri_flags_for_week(d)
        rows.append({"week_ending": d.isoformat(), **flags})
        d += dt.timedelta(days=7)
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(df)} weeks, {start}..{end})")
    # sanity: print the Ramadan weeks in the fixture window
    ram = df[df["ramadan"] == 1]["week_ending"].tolist()
    print("ramadan weeks sample:", ram[:3], "...", ram[-3:] if ram else "")


if __name__ == "__main__":
    main()
