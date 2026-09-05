"""The six baselines. All of them, before any ML (06-TRACK-B-MODEL.md Phase 1).

Each takes the fold's training frame (already as_of()-filtered) and returns one
forecast row per (city_code, item_code) for target_week, with p10/p50/p90.

Intervals: empirical quantiles of that series' own one-step residuals over a
trailing window. Crude, honest, and a real bar for the GBM's quantile heads.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

RESID_WINDOW = 26
Z80 = 1.2816  # normal fallback when a series has too few residuals

KEYS = ["city_code", "item_code"]


def _series_map(train: pd.DataFrame) -> dict[tuple[str, str], pd.Series]:
    out: dict[tuple[str, str], pd.Series] = {}
    for key, sub in train.sort_values("week_ending").groupby(KEYS, sort=False):
        s = pd.Series(
            sub["price_avg"].to_numpy(dtype=float),
            index=pd.to_datetime(sub["week_ending"]),
        )
        out[key] = s
    return out


def _empirical_interval(resid: np.ndarray, p50: float) -> tuple[float, float]:
    """p10/p90 from the series' own residual distribution; normal fallback."""
    r = resid[~np.isnan(resid)]
    if len(r) >= 8:
        lo, hi = np.quantile(r, [0.10, 0.90])
    elif len(r) >= 3:
        sd = float(np.std(r, ddof=1))
        lo, hi = -Z80 * sd, Z80 * sd
    else:
        lo, hi = -0.05 * abs(p50), 0.05 * abs(p50)
    return float(p50 + lo), float(p50 + hi)


def _pack(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Enforce p10 <= p50 <= p90 (Contract 2 invariant 1) by CLAMPING the bounds to
    # the point forecast — never by sorting the triple. For a baseline, p50 is the
    # model's actual forecast and the interval is derived from its own residuals; on
    # an inflating series both residual quantiles can sit on the same side of zero,
    # and sorting would silently replace the point forecast with an interval bound.
    df["p10"] = np.minimum(df["p10"], df["p50"])
    df["p90"] = np.maximum(df["p90"], df["p50"])
    df[["p10", "p50", "p90"]] = df[["p10", "p50", "p90"]].round(2)
    df["p10"] = df["p10"].clip(lower=0)
    return df


def _forecast_generic(train: pd.DataFrame, point_fn, resid_fn=None) -> pd.DataFrame:
    """point_fn(series) -> float|nan; resid_fn(series) -> residual array."""
    rows = []
    for (city, item), s in _series_map(train).items():
        s = s.dropna()
        if len(s) == 0:
            rows.append({"city_code": city, "item_code": item, "p10": np.nan,
                         "p50": np.nan, "p90": np.nan})
            continue
        p50 = point_fn(s)
        if p50 is None or not np.isfinite(p50):
            rows.append({"city_code": city, "item_code": item, "p10": np.nan,
                         "p50": np.nan, "p90": np.nan})
            continue
        resid = resid_fn(s) if resid_fn else np.diff(s.to_numpy()[-(RESID_WINDOW + 1):])
        p10, p90 = _empirical_interval(np.asarray(resid, dtype=float), float(p50))
        rows.append({"city_code": city, "item_code": item, "p10": p10, "p50": float(p50), "p90": p90})
    return _pack(rows)


# --- the six ------------------------------------------------------------------


def random_walk(train: pd.DataFrame, target_week: dt.date | None = None) -> pd.DataFrame:
    """y_hat = y[t]. The bar; on weekly prices it is hard to beat."""
    return _forecast_generic(train, lambda s: s.iloc[-1])


def seasonal_naive(train: pd.DataFrame, target_week: dt.date | None = None,
                   season: int = 52) -> pd.DataFrame:
    """y_hat = y[t+1-season]. The MASE denominator's model."""
    def point(s: pd.Series) -> float:
        if target_week is not None:
            want = pd.Timestamp(target_week) - pd.Timedelta(weeks=season)
            if want in s.index:
                return float(s.loc[want])
        if len(s) >= season:
            return float(s.iloc[-season])
        return float("nan")

    def resid(s: pd.Series) -> np.ndarray:
        y = s.to_numpy(dtype=float)
        if len(y) <= season:
            return np.array([np.nan])
        return (y[season:] - y[:-season])[-RESID_WINDOW:]

    return _forecast_generic(train, point, resid)


def seasonal_naive_4(train: pd.DataFrame, target_week: dt.date | None = None) -> pd.DataFrame:
    """Short-panel substitute denominator (R3 in 12-RISKS.md)."""
    return seasonal_naive(train, target_week, season=4)


def drift(train: pd.DataFrame, target_week: dt.date | None = None, k: int = 8) -> pd.DataFrame:
    """y_hat = y[t] + (y[t] - y[t-k]) / k. Cheap trend."""
    def point(s: pd.Series) -> float:
        y = s.to_numpy(dtype=float)
        if len(y) < k + 1:
            return float(y[-1])
        return float(y[-1] + (y[-1] - y[-1 - k]) / k)

    return _forecast_generic(train, point)


def seasonal_naive_ma(train: pd.DataFrame, target_week: dt.date | None = None,
                      window: int = 4) -> pd.DataFrame:
    """Mean of the last 4 weeks. Robust to one bad print."""
    return _forecast_generic(train, lambda s: float(s.iloc[-window:].mean()))


def ets(train: pd.DataFrame, target_week: dt.date | None = None,
        min_obs: int = 12) -> pd.DataFrame:
    """statsmodels ExponentialSmoothing per series (additive trend, no season —
    52-week seasonality needs 104+ obs, which most series do not have)."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    rows = []
    for (city, item), s in _series_map(train).items():
        s = s.dropna()
        p50 = np.nan
        resid = np.array([np.nan])
        if len(s) >= min_obs:
            try:
                y = s.to_numpy(dtype=float)
                model = ExponentialSmoothing(
                    y, trend="add", seasonal=None, initialization_method="estimated"
                ).fit(optimized=True)
                p50 = float(model.forecast(1)[0])
                resid = np.asarray(model.resid, dtype=float)[-RESID_WINDOW:]
            except Exception:
                p50 = float(s.iloc[-1])  # fall back to RW rather than dropping the series
                resid = np.diff(s.to_numpy()[-(RESID_WINDOW + 1):])
        elif len(s):
            p50 = float(s.iloc[-1])
            resid = np.diff(s.to_numpy()[-(RESID_WINDOW + 1):])
        if not np.isfinite(p50):
            rows.append({"city_code": city, "item_code": item, "p10": np.nan,
                         "p50": np.nan, "p90": np.nan})
            continue
        p10, p90 = _empirical_interval(resid, p50)
        rows.append({"city_code": city, "item_code": item, "p10": p10, "p50": p50, "p90": p90})
    return _pack(rows)


def arima(train: pd.DataFrame, target_week: dt.date | None = None,
          min_obs: int = 20, order_cache: dict | None = None) -> pd.DataFrame:
    """Per-series ARIMA with a small order search, cached per fold.

    Slow by nature; orders are cached so a re-fit within the same backtest reuses
    the selected order instead of re-searching.
    """
    from statsmodels.tsa.arima.model import ARIMA

    cache = order_cache if order_cache is not None else {}
    candidates = [(1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 0)]
    rows = []
    for (city, item), s in _series_map(train).items():
        s = s.dropna()
        p50, resid = np.nan, np.array([np.nan])
        if len(s) >= min_obs:
            y = s.to_numpy(dtype=float)
            order = cache.get((city, item))
            try:
                if order is None:
                    best, best_aic = None, np.inf
                    for cand in candidates:
                        try:
                            fit = ARIMA(y, order=cand).fit()
                            if fit.aic < best_aic:
                                best, best_aic = cand, fit.aic
                        except Exception:
                            continue
                    order = best or (1, 1, 0)
                    cache[(city, item)] = order
                fit = ARIMA(y, order=order).fit()
                p50 = float(fit.forecast(1)[0])
                resid = np.asarray(fit.resid, dtype=float)[-RESID_WINDOW:]
            except Exception:
                p50 = float(y[-1])
                resid = np.diff(y[-(RESID_WINDOW + 1):])
        elif len(s):
            p50 = float(s.iloc[-1])
            resid = np.diff(s.to_numpy()[-(RESID_WINDOW + 1):])
        if not np.isfinite(p50):
            rows.append({"city_code": city, "item_code": item, "p10": np.nan,
                         "p50": np.nan, "p90": np.nan})
            continue
        p10, p90 = _empirical_interval(resid, p50)
        rows.append({"city_code": city, "item_code": item, "p10": p10, "p50": p50, "p90": p90})
    return _pack(rows)


BASELINES = {
    "random_walk": random_walk,
    "seasonal_naive": seasonal_naive,
    "drift": drift,
    "seasonal_naive_ma": seasonal_naive_ma,
    "ets": ets,
    "arima": arima,
}

FAST_BASELINES = {k: BASELINES[k] for k in ("random_walk", "seasonal_naive", "drift", "seasonal_naive_ma")}
