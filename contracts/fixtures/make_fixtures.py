"""Bhao fixture generator — schema-valid synthetic data with nine planted pathologies.

Run:  python -m contracts.fixtures.make_fixtures [--out contracts/fixtures]

Deterministic: seed 20260824, fixed dates, no wall-clock anywhere in the values.
B trains on these before any real data exists; C builds the whole app on them.
Values are plausible but obviously synthetic, and `model_registry.json` carries
`meta.is_fixture = true` so C's banner fires (03-CONTRACTS.md §Fixtures).

Planted pathologies (05-TRACK-A-INGEST.md):
  1. ragged series start      — items 024, 040, 042 begin 40 weeks late
  2. missing cells            — ~4% of rows carry null prices ("-" in the real sheet)
  3. whole city missing       — city 13 (Larkana) absent for 6 consecutive weeks
  4. item renamed mid-series  — item 004 carries two PBS aliases
  5. a revision               — one key has revision 0 AND 1, differing ~3%
  6. administered step change — petrol 047: +18% in one week, flat either side
  7. variance regime shift    — potatoes 021: weekly sigma ×4 from week index 100
  8. extreme scale spread     — match box 044 ≈ Rs 2; gas charges 051 ≈ Rs 17,000
  9. unicode                  — real Urdu labels, item 033 contains a ZWNJ
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.item_catalog import ITEM_BY_CODE, ITEMS, SPI_BASKET_CODES

SEED = 20260824
N_WEEKS = 156
LAST_WEEK = dt.date(2026, 8, 20)
FIXTURE_RUN_TS = "2026-08-24T06-00-00Z"
REVISION_INGEST_TS = "2026-08-24T06:00:00Z"
FIXTURE_SOURCE = "pbs_spi_annex"
FIXTURE_URL = "https://fixture.bhao.example/{stem}/{fname}"

FIRST_WEEK = LAST_WEEK - dt.timedelta(weeks=N_WEEKS - 1)
assert FIRST_WEEK == dt.date(2023, 8, 31) and FIRST_WEEK.weekday() == 3  # Thursday

WEEKS: list[dt.date] = [FIRST_WEEK + dt.timedelta(weeks=i) for i in range(N_WEEKS)]

# pathology knobs
RAGGED_CODES = {"024", "040", "042"}
RAGGED_START = 40
MISSING_FRAC = 0.04
MISSING_CITY = "13"
MISSING_CITY_WEEKS = WEEKS[80:86]  # six consecutive weeks
RENAME_CODE = "004"
REVISION_KEY = (WEEKS[100], "05", "019")  # (week_ending, Lahore, Onions)
REVISION_DELTA = 0.03
ADMIN_STEP_CODE = "047"  # Petrol Super
ADMIN_STEP_WEEK = 120
ADMIN_STEP_PCT = 0.18
VARIANCE_CODE = "021"  # Potatoes
VARIANCE_WEEK = 100
VARIANCE_MULT = 4.0
SCALE_LOW_CODE = "044"
SCALE_HIGH_CODE = "051"

PROVINCES = {
    "00": ("Pakistan (national)", "پاکستان (قومی)"),
    "01": ("Islamabad Capital Territory", "اسلام آباد دارالحکومت علاقہ"),
    "02": ("Punjab", "پنجاب"),
    "03": ("Punjab", "پنجاب"),
    "04": ("Punjab", "پنجاب"),
    "05": ("Punjab", "پنجاب"),
    "06": ("Punjab", "پنجاب"),
    "07": ("Punjab", "پنجاب"),
    "08": ("Punjab", "پنجاب"),
    "09": ("Punjab", "پنجاب"),
    "10": ("Sindh", "سندھ"),
    "11": ("Sindh", "سندھ"),
    "12": ("Sindh", "سندھ"),
    "13": ("Sindh", "سندھ"),
    "14": ("Khyber Pakhtunkhwa", "خیبر پختونخوا"),
    "15": ("Khyber Pakhtunkhwa", "خیبر پختونخوا"),
    "16": ("Balochistan", "بلوچستان"),
    "17": ("Balochistan", "بلوچستان"),
}

CITIES = [
    ("00", "National", "قومی", None, None, 0),
    ("01", "Islamabad", "اسلام آباد", 33.6844, 73.0479, 1),
    ("02", "Rawalpindi", "راولپنڈی", 33.5651, 73.0169, 2),
    ("03", "Gujranwala", "گوجرانوالہ", 32.1877, 74.1945, 3),
    ("04", "Sialkot", "سیالکوٹ", 32.4945, 74.5229, 4),
    ("05", "Lahore", "لاہور", 31.5204, 74.3587, 5),
    ("06", "Faisalabad", "فیصل آباد", 31.4187, 73.0791, 6),
    ("07", "Sargodha", "سرگودها", 32.0836, 72.6711, 7),
    ("08", "Multan", "ملتان", 30.1575, 71.5249, 8),
    ("09", "Bahawalpur", "بہاولپور", 29.3956, 71.6836, 9),
    ("10", "Karachi", "کراچی", 24.8607, 67.0011, 10),
    ("11", "Hyderabad", "حیدرآباد", 25.3960, 68.3578, 11),
    ("12", "Sukkur", "سکھر", 27.7052, 68.8574, 12),
    ("13", "Larkana", "لاڑکانہ", 27.5589, 68.2123, 13),
    ("14", "Peshawar", "پشاور", 34.0151, 71.5249, 14),
    ("15", "Bannu", "بنوں", 32.9887, 70.6056, 15),
    ("16", "Quetta", "کوئٹہ", 30.1798, 66.9750, 16),
    ("17", "Khuzdar", "خضدار", 27.8006, 66.6258, 17),
]

CITY_LEVEL = {c[0]: 1.0 + 0.07 * math.sin(c[5]) for c in CITIES if c[0] != "00"}


def _ingest_ts(week: dt.date, revision: int = 0) -> pd.Timestamp:
    if revision == 0:
        return pd.Timestamp(week + dt.timedelta(days=2), tz="UTC") + pd.Timedelta(hours=6)
    return pd.Timestamp(REVISION_INGEST_TS)


def _url(stem: str, fname: str) -> str:
    return FIXTURE_URL.format(stem=stem, fname=fname)


def load_urdu_labels() -> dict[str, str]:
    here = Path(__file__).parent
    df = pd.read_csv(here / ".." / "item_labels_ur.csv")
    return dict(zip(df["item_en"], df["item_ur"], strict=False))


# ---------------------------------------------------------------------------
# cities / items
# ---------------------------------------------------------------------------


def generate_cities() -> pd.DataFrame:
    rows = [
        {
            "city_code": c[0],
            "city_en": c[1],
            "city_ur": c[2],
            "province_en": PROVINCES[c[0]][0],
            "province_ur": PROVINCES[c[0]][1],
            "lat": c[3],
            "lon": c[4],
            "pbs_order": np.int32(c[5]),
        }
        for c in CITIES
    ]
    return pd.DataFrame(rows)


def generate_items(urdu: dict[str, str]) -> pd.DataFrame:
    basket = set(SPI_BASKET_CODES)
    rows = []
    for it in ITEMS:
        if it.item_code not in basket:
            continue  # fixture panel covers the headline 867 only
        start = FIRST_WEEK + dt.timedelta(weeks=RAGGED_START if it.item_code in RAGGED_CODES else 0)
        rows.append(
            {
                "item_code": it.item_code,
                "item_en": it.item_en,
                "item_ur": urdu[it.item_en],
                "unit_raw": it.unit_raw,
                "unit_norm": it.unit_norm,
                "qty_norm": it.qty_norm,
                "category": it.category,
                "spi_weight": it.spi_weight,
                "is_food": it.is_food,
                "is_administered": it.is_administered,
                "pbs_aliases": list(it.pbs_aliases),
                "first_seen": start,
                "last_seen": LAST_WEEK,
                "notes": it.notes,
            }
        )
    df = pd.DataFrame(rows)
    df["qty_norm"] = df["qty_norm"].astype("float64")
    df["spi_weight"] = df["spi_weight"].astype("float64")
    return df


# ---------------------------------------------------------------------------
# prices_weekly — the core panel
# ---------------------------------------------------------------------------


def generate_prices(items_df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    urdu = load_urdu_labels()
    basket = {c: ITEM_BY_CODE[c] for c in SPI_BASKET_CODES}
    t_idx = np.arange(N_WEEKS)
    frames: list[pd.DataFrame] = []

    for code in SPI_BASKET_CODES:
        it = basket[code]
        sigma = it.weekly_sigma
        sig_vec = np.full(N_WEEKS, sigma)
        if code == VARIANCE_CODE:  # pathology 7: variance regime shift
            sig_vec[VARIANCE_WEEK:] = sigma * VARIANCE_MULT

        if it.is_administered and code == ADMIN_STEP_CODE:
            # pathology 6: flat, +18% in one week, flat either side; min=avg=max
            avg = np.where(
                t_idx < ADMIN_STEP_WEEK,
                it.base_price,
                round(it.base_price * (1 + ADMIN_STEP_PCT), 2),
            )
            spread = np.zeros(N_WEEKS)
        elif it.is_administered:
            steps = rng.random(N_WEEKS) < 0.03
            avg = it.base_price * np.exp(
                np.cumsum(np.where(steps, rng.normal(0.01, 0.005, N_WEEKS), 0.0))
            )
            spread = np.zeros(N_WEEKS)
        else:
            noise = rng.normal(0.0005, sig_vec)
            season_amp = 0.06 if it.category in ("vegetables", "fruit") else 0.015
            phase = float(rng.uniform(0, 2 * math.pi))
            logp = (
                np.log(it.base_price)
                + np.cumsum(noise) * (1 if code != VARIANCE_CODE else 1)
                + season_amp * np.sin(2 * math.pi * t_idx / 52 + phase)
            )
            avg = np.exp(logp)
            spread = rng.uniform(0.015, 0.09, N_WEEKS)

        avg = np.round(avg, 2)
        pmin = np.round(avg * (1 - spread), 2)
        pmax = np.round(avg * (1 + spread), 2)
        pmin = np.minimum(pmin, avg)
        pmax = np.maximum(pmax, avg)

        start_idx = RAGGED_START if code in RAGGED_CODES else 0
        item_ur = urdu[it.item_en]
        for city_code in [c[0] for c in CITIES if c[0] != "00"]:
            scale = CITY_LEVEL[city_code]
            cavg = np.round(avg * scale, 2)
            cmin = np.round(pmin * scale, 2)
            cmax = np.round(pmax * scale, 2)
            cmin = np.minimum(cmin, cavg)
            cmax = np.maximum(cmax, cavg)
            rows = {
                "week_ending": WEEKS[start_idx:],
                "city_code": [city_code] * (N_WEEKS - start_idx),
                "city_en": [next(c[1] for c in CITIES if c[0] == city_code)]
                * (N_WEEKS - start_idx),
                "city_ur": [next(c[2] for c in CITIES if c[0] == city_code)]
                * (N_WEEKS - start_idx),
                "item_code": [code] * (N_WEEKS - start_idx),
                "item_en": [it.item_en] * (N_WEEKS - start_idx),
                "item_ur": [item_ur] * (N_WEEKS - start_idx),
                "unit_raw": [it.unit_raw] * (N_WEEKS - start_idx),
                "unit_norm": [it.unit_norm] * (N_WEEKS - start_idx),
                "qty_norm": [it.qty_norm] * (N_WEEKS - start_idx),
                "price_min": cmin[start_idx:],
                "price_avg": cavg[start_idx:],
                "price_max": cmax[start_idx:],
                "price_per_unit": np.round(cavg[start_idx:] / it.qty_norm, 4),
                "source": [FIXTURE_SOURCE] * (N_WEEKS - start_idx),
                "source_url": [
                    _url("annex", f"Annex_{w.strftime('%d.%m.%Y')}.xlsx") for w in WEEKS[start_idx:]
                ],
                "ingested_at": [_ingest_ts(w) for w in WEEKS[start_idx:]],
                "revision": np.zeros(N_WEEKS - start_idx, dtype="int32"),
            }
            frames.append(pd.DataFrame(rows))

    panel = pd.concat(frames, ignore_index=True)

    # pathology 2: ~4% of rows null (the sheet printed "-")
    miss_rng = np.random.default_rng(SEED + 1)
    is_missing = miss_rng.random(len(panel)) < MISSING_FRAC
    for col in ("price_min", "price_avg", "price_max", "price_per_unit"):
        panel.loc[is_missing, col] = np.nan

    # a small set of rows where only min/max are absent but the average stands
    partial_rng = np.random.default_rng(SEED + 2)
    partial = partial_rng.random(len(panel)) < 0.005
    partial &= ~is_missing
    panel.loc[partial, ["price_min", "price_max"]] = np.nan

    # pathology 3: city 13 absent for six consecutive weeks — drop the rows entirely
    drop_mask = (panel["city_code"] == MISSING_CITY) & (
        panel["week_ending"].isin(MISSING_CITY_WEEKS)
    )
    panel = panel.loc[~drop_mask].reset_index(drop=True)

    # pathology 5: one key restated — append revision 1, 3% above revision 0
    wk, city, item = REVISION_KEY
    orig = panel[
        (panel["week_ending"] == wk)
        & (panel["city_code"] == city)
        & (panel["item_code"] == item)
        & (panel["revision"] == 0)
    ].iloc[0]
    rev1 = orig.to_dict()
    rev1["revision"] = np.int32(1)
    for col in ("price_min", "price_avg", "price_max", "price_per_unit"):
        rev1[col] = (
            round(float(orig[col]) * (1 + REVISION_DELTA), 2) if pd.notna(orig[col]) else np.nan
        )
    rev1["ingested_at"] = _ingest_ts(wk, revision=1)
    panel = pd.concat([panel, pd.DataFrame([rev1])], ignore_index=True)

    float_cols = ["qty_norm", "price_min", "price_avg", "price_max", "price_per_unit"]
    panel[float_cols] = panel[float_cols].astype("float64")
    panel["revision"] = panel["revision"].astype("int32")
    panel["ingested_at"] = panel["ingested_at"].astype("datetime64[us, UTC]")
    panel = panel.sort_values(["week_ending", "city_code", "item_code", "revision"]).reset_index(
        drop=True
    )
    return panel


# ---------------------------------------------------------------------------
# national_weekly — headline index + weighted national averages
# ---------------------------------------------------------------------------


def generate_national(panel: pd.DataFrame, items_df: pd.DataFrame) -> pd.DataFrame:
    weights = dict(zip(items_df["item_code"], items_df["spi_weight"], strict=False))
    rows = []

    national_by_week: dict[dt.date, dict[str, float]] = {}
    for week in WEEKS:
        wk = panel[(panel["week_ending"] == week) & (panel["revision"] == 0)]
        vals: dict[str, float] = {}
        for code, _w in weights.items():
            sub = wk[wk["item_code"] == code]
            avg = sub["price_avg"]
            if avg.notna().any():
                vals[code] = float(avg.dropna().mean())
        national_by_week[week] = vals

    # headline SPI index: slow inflation + noise, deterministic
    idx_rng = np.random.default_rng(SEED + 3)
    idx = 100.0 * np.exp(np.cumsum(idx_rng.normal(0.0022, 0.004, N_WEEKS)))
    idx = np.round(idx, 2)

    for i, week in enumerate(WEEKS):
        rows.append(
            {
                "week_ending": week,
                "item_code": "000",
                "price_this_week": float(idx[i]),
                "price_prev_week": float(idx[i - 1]) if i > 0 else np.nan,
                "price_same_week_last_year": float(idx[i - 52]) if i >= 52 else np.nan,
                "pct_change_wow": round((idx[i] / idx[i - 1] - 1) * 100, 2) if i > 0 else np.nan,
                "pct_change_yoy": round((idx[i] / idx[i - 52] - 1) * 100, 2) if i >= 52 else np.nan,
                "spi_weight_combined": 100.0,
                "spi_weight_lowest_quintile": 100.0,
                "source_url": _url("spi", f"SPI-Report_{week.strftime('%d.%m.%Y')}.xlsx"),
                "revision": np.int32(0),
                "ingested_at": _ingest_ts(week),
            }
        )
        for code, price in national_by_week[week].items():
            prev = national_by_week[WEEKS[i - 1]].get(code, np.nan) if i > 0 else np.nan
            yoy = national_by_week[WEEKS[i - 52]].get(code, np.nan) if i >= 52 else np.nan
            w = weights[code] or 0.0
            rows.append(
                {
                    "week_ending": week,
                    "item_code": code,
                    "price_this_week": price,
                    "price_prev_week": prev,
                    "price_same_week_last_year": yoy,
                    "pct_change_wow": (
                        round((price / prev - 1) * 100, 2)
                        if prev and not math.isnan(prev)
                        else np.nan
                    ),
                    "pct_change_yoy": (
                        round((price / yoy - 1) * 100, 2) if yoy and not math.isnan(yoy) else np.nan
                    ),
                    "spi_weight_combined": w,
                    "spi_weight_lowest_quintile": round(w * 1.18, 2),
                    "source_url": _url("spi", f"SPI-Report_{week.strftime('%d.%m.%Y')}.xlsx"),
                    "revision": np.int32(0),
                    "ingested_at": _ingest_ts(week),
                }
            )

    df = pd.DataFrame(rows)
    df["revision"] = df["revision"].astype("int32")
    df["ingested_at"] = df["ingested_at"].astype("datetime64[us, UTC]")
    return df


# ---------------------------------------------------------------------------
# wfp_monthly — long-history independent source
# ---------------------------------------------------------------------------

WFP_MARKETS = [
    ("Karachi", "Sindh", "Karachi", 24.8607, 67.0011),
    ("Lahore", "Punjab", "Lahore", 31.5204, 74.3587),
    ("Peshawar", "Khyber Pakhtunkhwa", "Peshawar", 34.0151, 71.5249),
    ("Quetta", "Balochistan", "Quetta", 30.1798, 66.9750),
    ("Islamabad", "Islamabad Capital Territory", "Islamabad", 33.6844, 73.0479),
    ("Multan", "Punjab", "Multan", 30.1575, 71.5249),
]

WFP_ITEMS = [
    # (item_wfp, item_code, unit, 2004 seed price PKR)
    ("Wheat flour", "001", "KG", 13.5),
    ("Rice (basmati, broken)", "003", "KG", 32.0),
    ("Sugar", "030", "KG", 24.0),
    ("Oil (cooking)", "011", "L", 48.0),
    ("Onions", "019", "KG", 12.0),
    ("Potatoes", "021", "KG", 11.0),
    ("Pulses", "040", "KG", 38.0),
    ("Meat (chicken, farm broiler, live)", "014", "KG", 88.0),
]


def generate_wfp() -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 4)
    months = pd.date_range("2004-01-01", "2026-07-01", freq="MS").date
    rows = []
    for market, admin1, admin2, lat, lon in WFP_MARKETS:
        for item_wfp, code, unit, seed_price in WFP_ITEMS:
            n = len(months)
            m = np.arange(n)
            logp = (
                math.log(seed_price)
                + 0.0062 * m
                + 0.05 * np.sin(2 * math.pi * (m % 12) / 12)
                + rng.normal(0, 0.02, n)
            )
            price = np.round(np.exp(logp), 2)
            usd = np.round(price / (60 + 0.9 * m / 12), 4)  # plausible PKR/USD drift
            for j, month in enumerate(months):
                rows.append(
                    {
                        "month": month,
                        "market_en": market,
                        "admin1": admin1,
                        "admin2": admin2,
                        "item_wfp": item_wfp,
                        "item_code": code,
                        "unit_wfp": unit,
                        "price": float(price[j]),
                        "usd_price": float(usd[j]),
                        "price_flag": "survey",
                        "price_type": "Retail",
                        "lat": lat,
                        "lon": lon,
                        "source_url": _url("wfp", "wfp_food_prices_pak.csv"),
                    }
                )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# forecasts / metrics / drift / registry
# ---------------------------------------------------------------------------

GBM_VERSION = "gbm-v1"
SNAIVE_VERSION = "sn-v1"
RW_VERSION = "rw-v1"


def _features_hash(city: str, item: str, made_on: dt.date) -> str:
    h = hashlib.sha256(f"{city}|{item}|{made_on.isoformat()}|feat-v1".encode()).hexdigest()
    return h[:16]


def generate_forecasts(panel: pd.DataFrame) -> pd.DataFrame:
    made_on = WEEKS[-2]
    target = WEEKS[-1]
    hist = panel[(panel["revision"] == 0) & (panel["week_ending"] <= made_on)]
    rows = []
    w52 = target - dt.timedelta(weeks=52)

    for (city, item), sub in hist.groupby(["city_code", "item_code"], sort=True):
        sub = sub.sort_values("week_ending")
        last = sub["price_avg"].iloc[-1]
        if pd.isna(last):
            continue
        recent = sub["price_avg"].tail(26)
        vol = float(recent.std(ddof=0) / max(last, 1e-9))
        e = max(1.2816 * vol, 0.005)
        snaive_val = sub.loc[sub["week_ending"] == w52, "price_avg"]
        sn = float(snaive_val.iloc[0]) if len(snaive_val) else np.nan
        drift_est = (
            0.3 * ((last / sub["price_avg"].iloc[-5]) ** 1 - 1)
            if len(sub) >= 5 and sub["price_avg"].iloc[-5]
            else 0.0
        )
        gbm_p50 = round(last * (1 + drift_est), 2)

        for model_name, version, p50, is_champion in (
            ("global_gbm", GBM_VERSION, gbm_p50, True),
            (
                "seasonal_naive",
                SNAIVE_VERSION,
                (round(sn, 2) if not math.isnan(sn) else np.nan),
                False,
            ),
            ("random_walk", RW_VERSION, round(float(last), 2), False),
        ):
            if pd.isna(p50):
                p10 = p90 = np.nan
            else:
                p10 = round(p50 * (1 - e), 2)
                p90 = round(p50 * (1 + e), 2)
            rows.append(
                {
                    "run_id": FIXTURE_RUN_TS,
                    "model_version": version,
                    "model_name": model_name,
                    "made_on": made_on,
                    "target_week": target,
                    "horizon": np.int32(1),
                    "city_code": city,
                    "item_code": item,
                    "p10": p10,
                    "p50": p50,
                    "p90": p90,
                    "is_champion": is_champion,
                    "features_hash": _features_hash(city, item, made_on),
                    "created_at": pd.Timestamp(REVISION_INGEST_TS),
                }
            )

    df = pd.DataFrame(rows)
    df = df.sample(frac=1.0, random_state=SEED).reset_index(
        drop=True
    )  # shuffled, still deterministic
    df["horizon"] = df["horizon"].astype("int32")
    df["created_at"] = df["created_at"].astype("datetime64[us, UTC]")
    return df


def _metrics_block(
    run_id,
    evaluated_on,
    target,
    model_name,
    model_version,
    scope,
    city_code,
    item_code,
    n_obs,
    errs,
    actuals,
    interval_hits,
    is_backtest,
):
    """errs = actual - p50 (signed); actuals = the actual prices; interval_hits = bool array."""
    if len(errs):
        ae = np.abs(errs)
        mae = float(ae.mean())
        rmse = float(np.sqrt((errs**2).mean()))
        smape = float(np.mean(2 * ae / np.maximum(np.abs(actuals) + np.abs(actuals - errs), 1e-9)))
        pin10 = float(np.mean(np.where(errs >= 0, 0.1 * errs, 0.9 * -errs)))
        pin50 = float(np.mean(0.5 * ae))
        pin90 = float(np.mean(np.where(errs >= 0, 0.9 * errs, 0.1 * -errs)))
        bias = float(errs.mean())
        cov = float(np.mean(interval_hits)) if len(interval_hits) else np.nan
    else:
        mae = rmse = smape = pin10 = pin50 = pin90 = bias = cov = np.nan
    return {
        "run_id": run_id,
        "evaluated_on": evaluated_on,
        "target_week": target,
        "model_name": model_name,
        "model_version": model_version,
        "scope": scope,
        "city_code": city_code,
        "item_code": item_code,
        "n_obs": np.int32(n_obs),
        "mae": None if mae != mae else round(mae, 4),
        "rmse": None if rmse != rmse else round(rmse, 4),
        "smape": None if smape != smape else round(smape * 100, 4),
        "pinball_10": None if pin10 != pin10 else round(pin10, 4),
        "pinball_50": None if pin50 != pin50 else round(pin50, 4),
        "pinball_90": None if pin90 != pin90 else round(pin90, 4),
        "coverage_80": None if cov != cov else round(cov, 4),
        "bias": None if bias != bias else round(bias, 4),
        # fixture MASE: |err| / (0.9 * MAE) per row, pooled — plausible, obviously synthetic
        "mase": None if mae != mae else round(float(np.mean(ae / max(0.9 * mae, 1e-9))), 4),
        "is_backtest": is_backtest,
    }


def generate_metrics(panel: pd.DataFrame, forecasts: pd.DataFrame) -> pd.DataFrame:
    target = WEEKS[-1]
    evaluated_on = dt.date(2026, 8, 24)
    actual = panel[(panel["revision"] == 0) & (panel["week_ending"] == target)]
    actual = actual.set_index(["city_code", "item_code"])["price_avg"]
    rows = []
    for model_name, msub in forecasts.groupby("model_name"):
        version = msub["model_version"].iloc[0]
        merged = msub.merge(
            actual.rename("actual"),
            left_on=["city_code", "item_code"],
            right_index=True,
            how="inner",
        )
        merged = merged[merged["actual"].notna() & merged["p50"].notna()]
        errs = (merged["actual"] - merged["p50"]).to_numpy()
        acts = merged["actual"].to_numpy()
        hits = (
            (merged["actual"] >= merged["p10"]) & (merged["actual"] <= merged["p90"])
        ).to_numpy()
        rows.append(
            _metrics_block(
                FIXTURE_RUN_TS,
                evaluated_on,
                target,
                model_name,
                version,
                "overall",
                None,
                None,
                len(errs),
                errs,
                acts,
                hits,
                False,
            )
        )
        if model_name == "global_gbm":
            cats = {it.item_code: it.category for it in ITEMS}
            merged["category"] = merged["item_code"].map(cats)
            for _cat, csub in merged.groupby("category"):
                cerrs = (csub["actual"] - csub["p50"]).to_numpy()
                cacts = csub["actual"].to_numpy()
                chits = (
                    (csub["actual"] >= csub["p10"]) & (csub["actual"] <= csub["p90"])
                ).to_numpy()
                rows.append(
                    _metrics_block(
                        FIXTURE_RUN_TS,
                        evaluated_on,
                        target,
                        model_name,
                        version,
                        "category",
                        None,
                        None,
                        len(cerrs),
                        cerrs,
                        cacts,
                        chits,
                        False,
                    )
                )
            for code in ("019", "001", "047", "020"):  # onions, flour, petrol, tomatoes
                isub = merged[merged["item_code"] == code]
                if len(isub):
                    ierrs = (isub["actual"] - isub["p50"]).to_numpy()
                    iacts = isub["actual"].to_numpy()
                    ihits = (
                        (isub["actual"] >= isub["p10"]) & (isub["actual"] <= isub["p90"])
                    ).to_numpy()
                    rows.append(
                        _metrics_block(
                            FIXTURE_RUN_TS,
                            evaluated_on,
                            target,
                            model_name,
                            version,
                            "item",
                            None,
                            code,
                            len(ierrs),
                            ierrs,
                            iacts,
                            ihits,
                            False,
                        )
                    )
            admin_codes = {it.item_code for it in ITEMS if it.is_administered}
            asub = merged[merged["item_code"].isin(admin_codes)]
            aerrs = (asub["actual"] - asub["p50"]).to_numpy()
            aacts = asub["actual"].to_numpy()
            ahits = ((asub["actual"] >= asub["p10"]) & (asub["actual"] <= asub["p90"])).to_numpy()
            rows.append(
                _metrics_block(
                    FIXTURE_RUN_TS,
                    evaluated_on,
                    target,
                    model_name,
                    version,
                    "administered",
                    None,
                    None,
                    len(aerrs),
                    aerrs,
                    aacts,
                    ahits,
                    False,
                )
            )
            lsub = merged[merged["city_code"] == "05"]
            lerrs = (lsub["actual"] - lsub["p50"]).to_numpy()
            lacts = lsub["actual"].to_numpy()
            lhits = ((lsub["actual"] >= lsub["p10"]) & (lsub["actual"] <= lsub["p90"])).to_numpy()
            rows.append(
                _metrics_block(
                    FIXTURE_RUN_TS,
                    evaluated_on,
                    target,
                    model_name,
                    version,
                    "city",
                    "05",
                    None,
                    len(lerrs),
                    lerrs,
                    lacts,
                    lhits,
                    False,
                )
            )
        # a backtest row per model
        rows.append(
            _metrics_block(
                FIXTURE_RUN_TS,
                evaluated_on,
                target,
                model_name,
                version,
                "overall",
                None,
                None,
                len(errs),
                errs * 1.02,
                acts,
                hits,
                True,
            )
        )
    df = pd.DataFrame(rows)
    df["n_obs"] = df["n_obs"].astype("int32")
    return df


def generate_drift() -> pd.DataFrame:
    checked_on = dt.date(2026, 8, 24)
    rows = [
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "residual",
            "subject": "overall",
            "test": "rolling_mase",
            "statistic": 1.38,
            "threshold": 1.14,
            "p_value": None,
            "fired": True,
            "severity": "critical",
            "window_start": dt.date(2026, 6, 12),
            "window_end": dt.date(2026, 8, 20),
            "note": (
                "Rolling MASE 1.38 vs backtest 0.91 since 2026-06-12; concentrated in "
                "vegetables (onions, tomatoes), consistent with a supply shock."
            ),
        },
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "feature",
            "subject": "lag_1_log_price",
            "test": "psi",
            "statistic": 0.18,
            "threshold": 0.10,
            "p_value": None,
            "fired": True,
            "severity": "warn",
            "window_start": dt.date(2026, 7, 23),
            "window_end": dt.date(2026, 8, 20),
            "note": (
                "Lag-1 log-price distribution shifted (PSI 0.18); driven by the onion "
                "supply shock, not a pipeline defect."
            ),
        },
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "residual",
            "subject": "11:019",
            "test": "page_hinkley",
            "statistic": 62.0,
            "threshold": 50.0,
            "p_value": None,
            "fired": True,
            "severity": "warn",
            "window_start": dt.date(2026, 7, 1),
            "window_end": dt.date(2026, 8, 20),
            "note": (
                "Page–Hinkley change point on Hyderabad onion residuals in the week "
                "ending 2026-07-16; mean error turned sharply negative."
            ),
        },
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "feature",
            "subject": "rolling_mean_4",
            "test": "psi",
            "statistic": 0.06,
            "threshold": 0.10,
            "p_value": None,
            "fired": False,
            "severity": "info",
            "window_start": dt.date(2026, 7, 23),
            "window_end": dt.date(2026, 8, 20),
            "note": "No actionable shift in the 4-week rolling mean feature.",
        },
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "coverage",
            "subject": "overall",
            "test": "coverage_gap",
            "statistic": 0.05,
            "threshold": 0.12,
            "p_value": None,
            "fired": False,
            "severity": "info",
            "window_start": dt.date(2026, 6, 5),
            "window_end": dt.date(2026, 8, 20),
            "note": "80% interval coverage within tolerance over the last 12 weeks.",
        },
        {
            "run_id": FIXTURE_RUN_TS,
            "checked_on": checked_on,
            "channel": "feature",
            "subject": "spread_ratio",
            "test": "ks",
            "statistic": 0.021,
            "threshold": 0.05,
            "p_value": 0.31,
            "fired": False,
            "severity": "info",
            "window_start": dt.date(2026, 7, 23),
            "window_end": dt.date(2026, 8, 20),
            "note": "No KS-detectable change in the min/max spread feature.",
        },
    ]
    return pd.DataFrame(rows)


def generate_registry() -> dict:
    return {
        "schema_version": 1,
        "updated_at": REVISION_INGEST_TS,
        "meta": {"is_fixture": True},
        "champion": GBM_VERSION,
        "models": [
            {
                "version": GBM_VERSION,
                "model_name": "global_gbm",
                "trained_at": "2026-08-24T05:52:10Z",
                "trained_through": "2026-08-13",
                "n_series": 867,
                "n_rows": 118431,
                "features_version": "feat-v1",
                "hyperparams": {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 400},
                "backtest": {
                    "folds": 12,
                    "mase": 0.91,
                    "smape": 3.94,
                    "coverage_80": 0.78,
                    "beat_seasonal_naive_pct_of_series": 0.62,
                },
                "artefact_path": "contracts/fixtures/registry_artefacts/gbm-v1/",
                "artefact_sha256": hashlib.sha256(b"bhao-fixture-gbm-v1").hexdigest(),
                "promoted_at": "2026-08-24T06:00:00Z",
                "promoted_because": (
                    "First champion: backtest MASE 0.91 vs seasonal-naive 1.00 "
                    "over 12 rolling-origin folds (fixture data)."
                ),
                "retired_at": None,
                "status": "champion",
            }
        ],
        "promotion_log": [
            {
                "at": "2026-08-24T06:00:00Z",
                "from": "seasonal_naive",
                "to": GBM_VERSION,
                "decision": "promote",
                "reason": (
                    "Initial promotion: the pooled GBM beat seasonal-naive by 9% MASE on "
                    "the fixture backtest, clearing the 3% gate."
                ),
                "trigger": "initial training",
            }
        ],
    }


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def generate_all(out_dir: Path) -> dict[str, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    urdu = load_urdu_labels()
    cities = generate_cities()
    items = generate_items(urdu)
    panel = generate_prices(items)
    national = generate_national(panel, items)
    wfp = generate_wfp()
    forecasts = generate_forecasts(panel)
    metrics = generate_metrics(panel, forecasts)
    drift = generate_drift()
    registry = generate_registry()

    named = {
        "cities": cities,
        "items": items,
        "prices_weekly": panel,
        "national_weekly": national,
        "wfp_monthly": wfp,
        "forecasts": forecasts,
        "metrics": metrics,
        "drift": drift,
    }
    for name, df in named.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    (out_dir / "model_registry.json").write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return named


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Bhao fixtures (deterministic).")
    ap.add_argument("--out", default=str(Path(__file__).parent), help="output directory")
    args = ap.parse_args()
    named = generate_all(Path(args.out))
    print(f"seed={SEED}")
    for name, df in named.items():
        print(f"  {name}.parquet: {len(df):>7} rows")


if __name__ == "__main__":
    main()
