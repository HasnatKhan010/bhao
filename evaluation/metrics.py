"""Metrics — the rules for every number B publishes (10-EVALUATION.md).

Headline: MASE = MAE(model) / MAE(seasonal_naive, in-sample, one-step, **on this
fold's training portion**, per series). The denominator IS the baseline: MASE < 1
literally means "better than naive".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SNAIVE_SEASON = 52  # weekly; falls back to 4 when the panel is shorter (R3, 12-RISKS)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    return float(np.abs(y_true[mask] - y_pred[mask]).mean())


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    return float(np.sqrt(((y_true[mask] - y_pred[mask]) ** 2).mean()))


def smape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """sMAPE × 100. Symmetric so it does not blow up near zero."""
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    t, p = y_true[mask], y_pred[mask]
    return float(np.mean(2 * np.abs(t - p) / np.maximum(np.abs(t) + np.abs(p), 1e-9)) * 100)


def pinball(y_true: np.ndarray, y_q: np.ndarray, alpha: float) -> float:
    """Proper score for a quantile forecast at level alpha."""
    mask = ~(np.isnan(y_true) | np.isnan(y_q))
    if not mask.any():
        return float("nan")
    d = y_true[mask] - y_q[mask]
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def coverage_80(y_true: np.ndarray, p10: np.ndarray, p90: np.ndarray) -> float:
    mask = ~(np.isnan(y_true) | np.isnan(p10) | np.isnan(p90))
    if not mask.any():
        return float("nan")
    return float(((y_true[mask] >= p10[mask]) & (y_true[mask] <= p90[mask])).mean())


def bias(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean signed error (actual − forecast). Positive = over-forecasting... as
    defined in Contract 2: positive bias means the model over-forecast (p50 > actual)."""
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if not mask.any():
        return float("nan")
    return float((y_pred[mask] - y_true[mask]).mean())


def snaive_denominator(series: pd.Series, season: int = SNAIVE_SEASON) -> float:
    """In-sample one-step seasonal-naive MAE on the TRAINING portion, per series.

    Falls back to season=4 when the training series is shorter than 2×52 weeks
    (a short panel is a fact, and the methodology must say which denominator was
    used — this function records it via `denominator_season`).
    """
    s = series.dropna()
    if len(s) < season + 2:
        season = 4
    if len(s) < season + 2:
        return float("nan")
    y = s.to_numpy(dtype=float)
    errs = np.abs(y[season:] - y[:-season])
    return float(errs.mean())


def denominator_season(series: pd.Series, season: int = SNAIVE_SEASON) -> int:
    """Which seasonal denominator actually applies to this series (52 or 4)."""
    return season if len(series.dropna()) >= season + 2 else 4


def rw_denominator(series: pd.Series) -> float:
    """In-sample one-step RANDOM-WALK MAE: mean|y_t − y_{t−1}| on the training data.

    Reported alongside the seasonal-naive denominator because on an inflating panel
    the lag-52 denominator is very weak — Pakistani retail prices carry ~9% headline
    YoY inflation (and +126% on onions in the verified week), so |y_t − y_{t−52}| is
    dominated by drift rather than by forecast difficulty. Against that denominator
    even a random walk scores MASE ≈ 0.15, which says nothing about the model. The
    lag-1 denominator is the bar 06-TRACK-B-MODEL.md actually calls hard to beat.
    """
    s = series.dropna()
    if len(s) < 3:
        return float("nan")
    y = s.to_numpy(dtype=float)
    return float(np.abs(y[1:] - y[:-1]).mean())


def mase_per_row(
    keys: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    denominators: pd.Series,
) -> np.ndarray:
    """Per-row scaled error: |err| / denominator(city, item). Rows with no
    denominator (series too short) are NaN and excluded from pooled MASE."""
    err = np.abs(y_true - y_pred)
    den = keys.merge(denominators.rename("den"), how="left", left_on=["city_code", "item_code"], right_index=True)["den"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        return err / den


def pooled_mase(
    keys: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    denominators: pd.Series,
) -> float:
    scaled = mase_per_row(keys, y_true, y_pred, denominators)
    scaled = scaled[~np.isnan(scaled)]
    return float(scaled.mean()) if len(scaled) else float("nan")


def beat_pct(keys_a, err_a, keys_b, err_b) -> float:
    """Fraction of series where model A's MAE < model B's MAE (e.g. gbm vs snaive)."""
    def per_series(keys, err):
        df = keys.copy()
        df["err"] = err
        return df.groupby(["city_code", "item_code"])["err"].mean()
    a = per_series(keys_a, np.abs(err_a))
    b = per_series(keys_b, np.abs(err_b))
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if not len(joined):
        return float("nan")
    return float((joined["a"] < joined["b"]).mean())
