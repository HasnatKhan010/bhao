"""Feature builder — every feature computable using only data with
week_ending <= made_on (and every fold calls as_of() before coming here).

Feature groups (06-TRACK-B-MODEL.md Phase 2):
  lags, rolling, momentum, volatility, spread, calendar (incl. Hijri),
  cross-sectional (LAGGED — "mean of the same item in other cities" at week t is a
  leak; at t-1 it is a feature), cross-item, static, series meta.

Versioned as feat-vN; recorded in model_registry.json.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FEATURES_VERSION = "feat-v1"

HERE = Path(__file__).parent
HIJRI_CSV = HERE / "hijri_weeks.csv"

LAGS = [1, 2, 3, 4, 5, 6, 7, 8, 12, 26, 52]
ROLLS = [4, 8, 13, 26, 52]

HARVEST_MONTHS = {
    "grains": {4, 5, 10, 11},
    "pulses": {3, 4},
    "sugar_sweeteners": {11, 12, 1},
    "vegetables": {12, 1, 2},
    "fruit": {6, 7, 8},
}

_hijri_cache: pd.DataFrame | None = None


def hijri_table() -> pd.DataFrame:
    global _hijri_cache
    if _hijri_cache is None:
        _hijri_cache = pd.read_csv(HIJRI_CSV, dtype={"week_ending": str})
        _hijri_cache["week_ending"] = pd.to_datetime(_hijri_cache["week_ending"]).dt.date
    return _hijri_cache


def build_features(panel: pd.DataFrame, items: pd.DataFrame | None = None,
                   national: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (week_ending, city_code, item_code): features computed from the
    past only; `target` = price_avg of target_week (week_ending + 7d).

    The input MUST already be as_of()-filtered by the caller (every fold does this);
    defensively, the latest-revision view is enforced here so a planted restatement
    can never split a series into two rows and corrupt its lags.
    """
    from contracts.schemas import latest_revision

    panel = latest_revision(panel)
    df = panel.sort_values(["city_code", "item_code", "week_ending"]).copy()
    df["week_dt"] = pd.to_datetime(df["week_ending"])
    g = df.groupby(["city_code", "item_code"], sort=False)
    p = df["price_avg"]

    # --- static ids first (later groups depend on category) ---
    if items is not None and len(items):
        im = items.set_index("item_code")
        df["category"] = df["item_code"].map(im["category"]).fillna("other")
        for col in ("is_administered", "unit_norm", "spi_weight"):
            if col in im.columns:
                df[col] = df["item_code"].map(im[col])
    else:
        df["category"] = "other"
    if "is_administered" not in df.columns:
        df["is_administered"] = False
    if "unit_norm" not in df.columns:
        df["unit_norm"] = "unit"
    if "spi_weight" not in df.columns:
        df["spi_weight"] = np.nan

    # --- lags ---
    for k in LAGS:
        df[f"lag_{k}"] = g["price_avg"].shift(k)

    # --- rolling stats (shift(1): statistics of the past, never the row itself) ---
    for w in ROLLS:
        for stat, name in (("mean", "roll_mean"), ("std", "roll_std"),
                           ("min", "roll_min"), ("max", "roll_max")):
            df[f"{name}_{w}"] = g["price_avg"].transform(
                lambda s, w=w, stat=stat: s.shift(1).rolling(w, min_periods=max(2, w // 2)).agg(stat)
            )
    base = df["roll_mean_52"].fillna(df["roll_mean_26"]).fillna(df["roll_mean_8"])
    sd = df["roll_std_52"].fillna(df["roll_std_26"]).replace(0, np.nan)
    df["zscore_vs_52"] = (df["price_avg"] - base) / sd

    # --- momentum ---
    df["diff_1"] = g["price_avg"].diff(1)
    df["diff_4"] = g["price_avg"].diff(4)
    df["diff_13"] = g["price_avg"].diff(13)
    df["pct_1"] = g["price_avg"].pct_change(1, fill_method=None)
    df["pct_4"] = g["price_avg"].pct_change(4, fill_method=None)
    sign = np.sign(g["price_avg"].diff(1))
    df["sign_changes_8"] = (
        (sign.notna() & (sign.diff() != 0))
        .astype(float)
        .groupby([df["city_code"], df["item_code"]])
        .transform(lambda s: s.rolling(8, min_periods=2).sum())
    )

    # --- volatility regime: sigma(4) / sigma(26) — the regime-shift signal ---
    s4 = g["price_avg"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).std())
    s26 = g["price_avg"].transform(lambda s: s.shift(1).rolling(26, min_periods=6).std())
    df["vol_ratio_4_26"] = s4 / s26.replace(0, np.nan)

    # --- spread: shop-level dispersion leads the average move ---
    df["spread"] = (df["price_max"] - df["price_min"]) / p.where(p > 0)
    df["spread_ma_4"] = g["spread"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean())
    df["spread_trend"] = df["spread"] - df["spread_ma_4"]

    # --- calendar ---
    wk = df["week_dt"].dt.isocalendar().week.astype(float)
    df["week_of_year_sin"] = np.sin(2 * np.pi * wk / 52.0)
    df["week_of_year_cos"] = np.cos(2 * np.pi * wk / 52.0)
    df["month"] = df["week_dt"].dt.month
    hj = hijri_table().rename(columns={"week_ending": "_hj_week"})
    df = df.merge(hj, left_on=df["week_dt"].dt.date, right_on="_hj_week", how="left")
    for c in ("ramadan", "eid_fitr", "eid_adha"):
        if c in df.columns:
            df[c] = df[c].fillna(0).astype(float)
    df["harvest_flag"] = [1 if m in HARVEST_MONTHS.get(cat, set()) else 0
                          for m, cat in zip(df["month"], df["category"])]

    # --- cross-sectional, LAGGED by one week (anti-leakage, 06 §Traps #2) ---
    # The lagged frame holds, for each df row, that series' values as of ONE WEEK
    # EARLIER — so every cross-sectional statistic is last week's knowledge.
    lagged = df[["week_dt", "city_code", "item_code", "price_avg"]].copy()
    lagged["week_dt"] = lagged["week_dt"] + pd.Timedelta(weeks=1)
    grp = lagged.groupby(["week_dt", "item_code"])["price_avg"]
    lagged["xs_item_mean_lag1"] = grp.transform("mean")
    lagged["rank_in_item_lag1"] = grp.rank(pct=True)
    df = df.merge(
        lagged[["week_dt", "city_code", "item_code", "xs_item_mean_lag1", "rank_in_item_lag1"]],
        on=["week_dt", "city_code", "item_code"], how="left",
    )
    df["xs_dev_lag1"] = df["price_avg"] / df["xs_item_mean_lag1"].replace(0, np.nan) - 1

    # --- cross-item: category mean (lagged), national SPI index (lagged) ---
    cat_map = (items.set_index("item_code")["category"] if items is not None and len(items)
               else pd.Series(dtype="object"))
    lagged_cat = df[["week_dt", "item_code"]].copy()
    lagged_cat["category"] = lagged_cat["item_code"].map(cat_map).fillna("other")
    lagged_cat["price_avg"] = df["price_avg"].to_numpy()
    lagged_cat["week_dt"] = lagged_cat["week_dt"] + pd.Timedelta(weeks=1)
    df = df.merge(
        lagged_cat.groupby(["week_dt", "category"])["price_avg"].mean().rename("cat_mean_lag1"),
        left_on=["week_dt", "category"], right_index=True, how="left",
    )
    if national is not None and len(national):
        nat = national[national["item_code"] == "000"][["week_ending", "price_this_week"]].copy()
        nat["week_dt"] = pd.to_datetime(nat["week_ending"]) + pd.Timedelta(weeks=1)
        df = df.merge(
            nat.rename(columns={"price_this_week": "spi_index_lag1"})[["week_dt", "spi_index_lag1"]],
            on="week_dt", how="left",
        )
        df["spi_index_lag1"] = df["spi_index_lag1"].ffill()
    else:
        df["spi_index_lag1"] = np.nan

    # --- series meta + target: computed on the FINAL frame (merges above replace
    # the frame, and a stale GroupBy would silently align against shuffled rows) ---
    g2 = df.groupby(["city_code", "item_code"], sort=False)
    df["n_obs"] = g2["price_avg"].cumcount() + 1
    df["missing_rate_26"] = g2["price_avg"].transform(
        lambda s: s.isna().rolling(26, min_periods=2).mean()
    )
    df["target_week"] = df["week_dt"] + pd.Timedelta(weeks=1)
    df["target"] = g2["price_avg"].shift(-1)
    df["target_log"] = np.log(df["target"].where(df["target"] > 0))
    return df


SKIP_COLS = {
    "week_ending", "week_dt", "target_week", "target", "target_log",
    "price_min", "price_avg", "price_max", "price_per_unit", "_hj_week",
    "city_en", "city_ur", "item_en", "item_ur", "unit_raw", "source",
    "source_url", "ingested_at", "revision", "key_merge", "rank_pct",
}


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Model-matrix columns: numeric builders + categorical ids, minus keys/targets/raw."""
    cols = []
    for c in df.columns:
        if c in SKIP_COLS:
            continue
        if pd.api.types.is_numeric_dtype(df[c]) or c in ("city_code", "item_code", "category", "unit_norm"):
            cols.append(c)
    return cols


CATEGORICAL_COLS = ["city_code", "item_code", "category", "unit_norm"]


def features_hash_row(row: pd.Series, cols: list[str]) -> str:
    import hashlib

    h = hashlib.sha256()
    for c in sorted(cols):
        h.update(f"{c}={row.get(c)};".encode())
    return h.hexdigest()[:16]
