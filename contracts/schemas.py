"""Bhao schemas — Contract 1 and Contract 2 as executable Pandera schemas.

If this file and 03-CONTRACTS.md disagree, **the prose wins and this code is a bug**.

Conventions (03-CONTRACTS.md):
- dates are ISO ``YYYY-MM-DD``; ``week_ending`` is always the Thursday surveyed to.
  Stored as pyarrow ``date32`` (pandas: object column of ``datetime.date``).
- timestamps are UTC ISO 8601; stored as ``timestamp[us, UTC]``.
- money is PKR float64, 2 dp, never a string.
- nulls are real nulls, never 0 / -1 / "N/A".
- codes are zero-padded strings ("01", "001"), never ints.
- extra columns are allowed and must be ignored by consumers (``strict=False``).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
import pandera as pa
from pandera import Check, Column

from contracts.enums import (
    CATEGORY,
    DRIFT_CHANNEL,
    DRIFT_TEST,
    SCOPE,
    SEVERITY,
    SOURCE,
    UNIT_NORM,
)

# ---------------------------------------------------------------------------
# shared checks
# ---------------------------------------------------------------------------

CODE2_CHECK = Check.str_matches(r"^\d{2}$")
CODE3_CHECK = Check.str_matches(r"^\d{3}$")
MONEY_CHECK = Check.ge(0, ignore_na=True)
QTY_CHECK = Check.gt(0, ignore_na=True)
IS_DATE = Check(
    lambda s: s.map(lambda v: isinstance(v, dt.date) and not isinstance(v, dt.datetime)),
    name="is_date",
)
IS_STR_LIST = Check(
    lambda s: s.map(
        lambda v: isinstance(v, (list, np.ndarray))
        and len(v) > 0
        and all(isinstance(x, str) for x in v)
    ),
    name="is_str_list",
)
IGNORE_NA = dict(ignore_na=True)

PRICE_KEYS = ["week_ending", "city_code", "item_code", "revision"]
TS_DTYPE = "datetime64[us, UTC]"


# ---------------------------------------------------------------------------
# helpers every consumer of the panel uses
# ---------------------------------------------------------------------------


def week_ending_as_dates(series: pd.Series) -> pd.Series:
    """Coerce a week_ending column (dates or datetimes) to object-of-datetime.date."""

    def one(v: Any) -> dt.date | None:
        if v is None or v is pd.NaT:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, dt.datetime):
            return v.date()
        if isinstance(v, dt.date):
            return v
        if isinstance(v, str):
            return dt.date.fromisoformat(v)
        return None

    return series.map(one)


def latest_revision(df: pd.DataFrame) -> pd.DataFrame:
    """Current view of the panel: max ``revision`` per (week_ending, city_code, item_code)."""
    keys = ["week_ending", "city_code", "item_code"]
    ordered = df.sort_values(keys + ["revision"], kind="mergesort")
    return ordered.drop_duplicates(keys, keep="last").reset_index(drop=True)


def as_of(df: pd.DataFrame, known_on: dt.date | dt.datetime | str) -> pd.DataFrame:
    """Anti-leakage view: only what was *knowable* at ``known_on`` (made_on).

    Two kinds of row, two rules:

    - **revision 0** (first publication): knowable iff ``week_ending <= known_on``.
      PBS publishes the Friday after the surveyed Thursday, so the made_on week's
      own rows are knowable at forecast time. When the panel is built by backfill,
      ``ingested_at`` records when *we* fetched a file, not when PBS published it —
      gating revision-0 rows on ``ingested_at`` would wrongly hide most of the
      recovered history.
    - **revision >= 1** (restatement): knowable iff ``week_ending <= known_on``
      **and** ``ingested_at.date() <= known_on``. A restated figure that landed
      after the forecast was made is not knowable, and training on it is the leak
      that makes every metric in the project quietly false.

    Among the survivors, only the highest revision per series key is kept. Every
    backtest fold calls this.
    """
    if isinstance(known_on, dt.datetime):
        known_on_d: dt.date = known_on.date()
    elif isinstance(known_on, dt.date):
        known_on_d = known_on
    else:
        known_on_d = dt.date.fromisoformat(str(known_on))
    known_ts = pd.Timestamp(known_on_d)

    weeks = pd.to_datetime(df["week_ending"])
    rev = df["revision"] if "revision" in df.columns else 0
    ingested = pd.to_datetime(df["ingested_at"], utc=True).dt.date
    knowable = (weeks <= known_ts) & ((rev == 0) | (ingested <= known_on_d))
    return latest_revision(df.loc[knowable].copy())


# ---------------------------------------------------------------------------
# dataframe-level business rules
# ---------------------------------------------------------------------------


def _price_order_rule(df: pd.DataFrame) -> pd.Series:
    """Where all three are present: price_min <= price_avg <= price_max."""
    lo, mid, hi = df["price_min"], df["price_avg"], df["price_max"]
    ok = pd.Series(True, index=df.index)
    ok &= ~(lo.notna() & mid.notna() & (lo > mid))
    ok &= ~(hi.notna() & mid.notna() & (mid > hi))
    ok &= ~(lo.notna() & hi.notna() & (lo > hi))
    return ok


def _quantile_order_rule(df: pd.DataFrame) -> pd.Series:
    """forecasts: p10 <= p50 <= p90 where all present."""
    lo, mid, hi = df["p10"], df["p50"], df["p90"]
    ok = pd.Series(True, index=df.index)
    ok &= ~(lo.notna() & mid.notna() & (lo > mid))
    ok &= ~(hi.notna() & mid.notna() & (mid > hi))
    ok &= ~(lo.notna() & hi.notna() & (lo > hi))
    return ok


def _scope_key_consistent(df: pd.DataFrame) -> pd.Series:
    """city_code/item_code null exactly when the scope does not include them."""
    scope = df["scope"]
    want_city = scope.isin(["city", "city_item"])
    want_item = scope.isin(["item", "city_item"])
    ok = (df["city_code"].notna() == want_city) & (df["item_code"].notna() == want_item)
    ok &= ~((scope == "city_item") & (df["city_code"].isna() | df["item_code"].isna()))
    ok &= ~((scope == "administered") & (df["city_code"].notna() | df["item_code"].notna()))
    return ok


# ---------------------------------------------------------------------------
# CONTRACT 1 — the panel (A produces, B and C consume)
# ---------------------------------------------------------------------------

PRICES_WEEKLY = pa.DataFrameSchema(
    {
        "week_ending": Column(object, IS_DATE, nullable=False),
        "city_code": Column(object, CODE2_CHECK, nullable=False),
        "city_en": Column(object, nullable=False),
        "city_ur": Column(object, nullable=False),
        "item_code": Column(object, CODE3_CHECK, nullable=False),
        "item_en": Column(object, nullable=False),
        "item_ur": Column(object, nullable=False),
        "unit_raw": Column(object, nullable=False),
        "unit_norm": Column(object, Check.isin(UNIT_NORM), nullable=False),
        "qty_norm": Column("float64", QTY_CHECK, nullable=False),
        "price_min": Column("float64", MONEY_CHECK, nullable=True),
        "price_avg": Column("float64", MONEY_CHECK, nullable=True),
        "price_max": Column("float64", MONEY_CHECK, nullable=True),
        "price_per_unit": Column("float64", MONEY_CHECK, nullable=True),
        "source": Column(object, Check.isin(SOURCE), nullable=False),
        "source_url": Column(object, nullable=False),
        "ingested_at": Column(TS_DTYPE, nullable=False),
        "revision": Column("int32", Check.ge(0), nullable=False),
    },
    checks=Check(_price_order_rule, name="price_min_le_avg_le_max"),
    unique=[PRICE_KEYS],
    strict=False,
    name="prices_weekly",
)

ITEMS = pa.DataFrameSchema(
    {
        "item_code": Column(object, CODE3_CHECK, nullable=False),
        "item_en": Column(object, nullable=False),
        "item_ur": Column(object, nullable=False),
        "unit_raw": Column(object, nullable=False),
        "unit_norm": Column(object, Check.isin(UNIT_NORM), nullable=False),
        "qty_norm": Column("float64", QTY_CHECK, nullable=False),
        "category": Column(object, Check.isin(CATEGORY), nullable=False),
        "spi_weight": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "is_food": Column("bool", nullable=False),
        "is_administered": Column("bool", nullable=False),
        "pbs_aliases": Column(object, IS_STR_LIST, nullable=False),
        "first_seen": Column(object, IS_DATE, nullable=False),
        "last_seen": Column(object, IS_DATE, nullable=False),
        "notes": Column(object, nullable=True),
    },
    unique=["item_code"],
    strict=False,
    name="items",
)

CITIES = pa.DataFrameSchema(
    {
        "city_code": Column(object, CODE2_CHECK, nullable=False),
        "city_en": Column(object, nullable=False),
        "city_ur": Column(object, nullable=False),
        "province_en": Column(object, nullable=False),
        "province_ur": Column(object, nullable=False),
        "lat": Column("float64", Check.between(-90, 90, **IGNORE_NA), nullable=True),
        "lon": Column("float64", Check.between(-180, 180, **IGNORE_NA), nullable=True),
        "pbs_order": Column("int32", Check.ge(0), nullable=False),
    },
    unique=["city_code"],
    strict=False,
    name="cities",
)

NATIONAL_WEEKLY = pa.DataFrameSchema(
    {
        "week_ending": Column(object, IS_DATE, nullable=False),
        "item_code": Column(object, CODE3_CHECK, nullable=False),
        "price_this_week": Column("float64", MONEY_CHECK, nullable=True),
        "price_prev_week": Column("float64", MONEY_CHECK, nullable=True),
        "price_same_week_last_year": Column("float64", MONEY_CHECK, nullable=True),
        "pct_change_wow": Column("float64", nullable=True),
        "pct_change_yoy": Column("float64", nullable=True),
        "spi_weight_combined": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "spi_weight_lowest_quintile": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "source_url": Column(object, nullable=False),
        "revision": Column("int32", Check.ge(0), nullable=False),
    },
    unique=[["week_ending", "item_code", "revision"]],
    strict=False,
    name="national_weekly",
)

WFP_MONTHLY = pa.DataFrameSchema(
    {
        "month": Column(object, IS_DATE, nullable=False),
        "market_en": Column(object, nullable=False),
        "admin1": Column(object, nullable=False),
        "admin2": Column(object, nullable=True),
        "item_wfp": Column(object, nullable=False),
        "item_code": Column(object, CODE3_CHECK, nullable=True),
        "unit_wfp": Column(object, nullable=False),
        "price": Column("float64", MONEY_CHECK, nullable=True),
        "usd_price": Column("float64", MONEY_CHECK, nullable=True),
        "price_flag": Column(object, nullable=True),
        "price_type": Column(object, nullable=True),
        "lat": Column("float64", Check.between(-90, 90, **IGNORE_NA), nullable=True),
        "lon": Column("float64", Check.between(-180, 180, **IGNORE_NA), nullable=True),
        "source_url": Column(object, nullable=False),
    },
    strict=False,
    name="wfp_monthly",
)

# ---------------------------------------------------------------------------
# CONTRACT 2 — forecasts and health (B produces, C consumes)
# ---------------------------------------------------------------------------

FORECASTS = pa.DataFrameSchema(
    {
        "run_id": Column(object, nullable=False),
        "model_version": Column(object, nullable=False),
        "model_name": Column(object, nullable=False),
        "made_on": Column(object, IS_DATE, nullable=False),
        "target_week": Column(object, IS_DATE, nullable=False),
        "horizon": Column("int32", Check.ge(1), nullable=False),
        "city_code": Column(object, CODE2_CHECK, nullable=False),
        "item_code": Column(object, CODE3_CHECK, nullable=False),
        "p10": Column("float64", MONEY_CHECK, nullable=True),
        "p50": Column("float64", MONEY_CHECK, nullable=True),
        "p90": Column("float64", MONEY_CHECK, nullable=True),
        "is_champion": Column("bool", nullable=False),
        "features_hash": Column(object, nullable=False),
        "created_at": Column(TS_DTYPE, nullable=False),
    },
    checks=Check(_quantile_order_rule, name="p10_le_p50_le_p90"),
    unique=[["run_id", "model_name", "city_code", "item_code", "target_week"]],
    strict=False,
    name="forecasts",
)

METRICS = pa.DataFrameSchema(
    {
        "run_id": Column(object, nullable=False),
        "evaluated_on": Column(object, IS_DATE, nullable=False),
        "target_week": Column(object, IS_DATE, nullable=False),
        "model_name": Column(object, nullable=False),
        "model_version": Column(object, nullable=False),
        "scope": Column(object, Check.isin(SCOPE), nullable=False),
        "city_code": Column(object, CODE2_CHECK, nullable=True),
        "item_code": Column(object, CODE3_CHECK, nullable=True),
        "n_obs": Column("int32", Check.ge(0), nullable=False),
        "mase": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "smape": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "mae": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "rmse": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "pinball_10": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "pinball_50": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "pinball_90": Column("float64", Check.ge(0, **IGNORE_NA), nullable=True),
        "coverage_80": Column("float64", Check.between(0, 1, **IGNORE_NA), nullable=True),
        "bias": Column("float64", nullable=True),
        "is_backtest": Column("bool", nullable=False),
    },
    checks=Check(_scope_key_consistent, name="scope_keys_consistent", ignore_na=False),
    strict=False,
    name="metrics",
)

DRIFT = pa.DataFrameSchema(
    {
        "run_id": Column(object, nullable=False),
        "checked_on": Column(object, IS_DATE, nullable=False),
        "channel": Column(object, Check.isin(DRIFT_CHANNEL), nullable=False),
        "subject": Column(object, nullable=False),
        "test": Column(object, Check.isin(DRIFT_TEST), nullable=False),
        "statistic": Column("float64", nullable=True),
        "threshold": Column("float64", nullable=True),
        "p_value": Column("float64", Check.between(0, 1, **IGNORE_NA), nullable=True),
        "fired": Column("bool", nullable=False),
        "severity": Column(object, Check.isin(SEVERITY), nullable=False),
        "window_start": Column(object, IS_DATE, nullable=True),
        "window_end": Column(object, IS_DATE, nullable=True),
        "note": Column(object, nullable=False),
    },
    strict=False,
    name="drift",
)

# name -> schema, for validate_frame()
SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "prices_weekly": PRICES_WEEKLY,
    "items": ITEMS,
    "cities": CITIES,
    "national_weekly": NATIONAL_WEEKLY,
    "wfp_monthly": WFP_MONTHLY,
    "forecasts": FORECASTS,
    "metrics": METRICS,
    "drift": DRIFT,
}

# backwards-compatible alias
ALL_MODELS = SCHEMAS

PANEL_SCHEMAS = {
    k: SCHEMAS[k] for k in ("prices_weekly", "items", "cities", "national_weekly", "wfp_monthly")
}
FORECAST_SCHEMAS = {k: SCHEMAS[k] for k in ("forecasts", "metrics", "drift")}


# ---------------------------------------------------------------------------
# convenience validators
# ---------------------------------------------------------------------------


def validate_frame(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Validate a dataframe against a named contract schema. Hard fail, loud error."""
    return SCHEMAS[name].validate(df, lazy=True)


def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "prices_weekly")


def validate_forecasts(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "forecasts")


def validate_metrics(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "metrics")


def validate_drift(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "drift")


def validate_cities(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "cities")


def validate_items(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "items")


def validate_national(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "national_weekly")


def validate_wfp(df: pd.DataFrame) -> pd.DataFrame:
    return validate_frame(df, "wfp_monthly")
