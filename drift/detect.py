"""Drift detection — the centrepiece (06-TRACK-B-MODEL.md Phase 5, 10-EVALUATION.md).

Two channels, four tests, every row lands in drift.parquet:

  feature drift   — PSI per numeric feature (top-20 by gain), KS two-sample
  residual drift  — rolling MASE on the live champion (2-week rule),
                    Page–Hinkley change point on the residual stream,
                    coverage gap on the 80% intervals

Every fired row carries a human `note` — a sentence a journalist could quote,
because C renders these verbatim on /drift.

Do NOT simulate drift on real data. The fixture's planted variance shift is what
tests the detector (drift/tests in tests/model/).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from scipy import stats

from drift import thresholds as T


def psi(reference: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Population Stability Index between two numeric samples.

    Bands (industry standard): <0.1 none, 0.1–0.25 warn, >0.25 critical.
    """
    ref = reference[~np.isnan(reference)]
    cur = current[~np.isnan(current)]
    if len(ref) < 20 or len(cur) < 5:
        return 0.0
    edges = np.quantile(ref, np.linspace(0, 1, n_bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    r_hist, _ = np.histogram(ref, bins=edges)
    c_hist, _ = np.histogram(cur, bins=edges)
    r_pct = r_hist / r_hist.sum()
    c_pct = c_hist / c_hist.sum()
    # clamp zero cells to a floor so the log never explodes
    r_pct = np.clip(r_pct, 1e-6, None)
    c_pct = np.clip(c_pct, 1e-6, None)
    return float(np.sum((c_pct - r_pct) * np.log(c_pct / r_pct)))


def ks_two_sample(reference: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    ref = reference[~np.isnan(reference)]
    cur = current[~np.isnan(current)]
    if len(ref) < 10 or len(cur) < 5:
        return 0.0, 1.0
    stat, p = stats.ks_2samp(ref, cur)
    return float(stat), float(p)


def rolling_mase(fc: pd.DataFrame, metrics_backtest_mase: float) -> tuple[float, int]:
    """Rolling 8-week MASE of the live champion vs the backtest MASE.

    Fires if > 1.25x the backtest MASE for 2 consecutive weeks. The 2-week rule
    kills single-shock false alarms.
    """
    window = T.ROLLING_MASE_WINDOW
    m = fc[fc["model_name"].eq("global_gbm") | fc["model_name"].eq(fc["model_name"].iloc[0])]
    if m.empty or metrics_backtest_mase is None or not np.isfinite(metrics_backtest_mase):
        return float("nan"), 0
    latest = m.sort_values("target_week").tail(window)
    if latest.empty:
        return float("nan"), 0
    mases = latest["mase"].dropna()
    if mases.empty:
        return float("nan"), 0
    return float(mases.mean()), int(mases.size)


def page_hinkley(residuals: np.ndarray, delta: float = T.PH_DELTA,
                 lam: float = T.PH_LAMBDA) -> tuple[bool, float]:
    """Page–Hinkley change-point on the |residual| stream.

    A variance regime shift is a level shift in |residual|, so the detector runs on
    absolute residuals with both running-max and running-min tracking: it fires on
    a sustained INCREASE (m − N) or DECREASE (M − m) in |residual|. Tuned on the
    fixture's planted shift (see drift/thresholds.py).
    """
    r = np.abs(residuals[~np.isnan(residuals)])
    if len(r) < T.PH_MIN_OBS:
        return False, 0.0
    m = 0.0
    M = -np.inf
    N = np.inf
    for x in r:
        m += x - delta
        M = max(M, m)
        N = min(N, m)
        if (M - m) > lam or (m - N) > lam:
            return True, float(max(M - m, m - N))
    return False, float(max(M - m, m - N))


def coverage_gap(metrics: pd.DataFrame) -> tuple[float, int]:
    """|coverage_80 − 0.80| over the last 12 weeks of live scoring."""
    m = metrics[metrics["scope"] == "overall"]
    m = m[m["is_backtest"] == False]  # noqa: E712
    window = m.sort_values("target_week").tail(T.COVERAGE_WINDOW)
    cov = window["coverage_80"].dropna()
    if cov.empty:
        return float("nan"), 0
    return float(abs(cov.mean() - 0.80)), int(cov.size)


def severity_for(test: str, statistic: float, fired: bool) -> str:
    if not fired:
        return "info"
    if test == "psi":
        return "critical" if statistic > T.PSI_WARN else "warn"
    return "critical" if test in ("rolling_mase",) else "warn"


def check_feature_drift(reference: pd.DataFrame, current: pd.DataFrame,
                        top_features: list[str], run_id: str,
                        checked_on: dt.date) -> list[dict]:
    """PSI + KS on the top-gain features. PSI on 200 features gives 200 alerts and
    no information — only the top 20 by gain are tested (10-EVALUATION.md)."""
    rows = []
    for f in top_features[:20]:
        if f not in reference.columns or f not in current.columns:
            continue
        if not pd.api.types.is_numeric_dtype(reference[f]):
            continue
        stat = psi(reference[f].to_numpy(float), current[f].to_numpy(float))
        ks_stat, p = ks_two_sample(reference[f].to_numpy(float), current[f].to_numpy(float))
        for test, value, threshold, pv in (
            ("psi", stat, T.PSI_NONE, None),
            ("ks", ks_stat, 0.05, p),
        ):
            fired = (test == "psi" and value > T.PSI_NONE) or (test == "ks" and pv is not None and pv < T.KS_ALPHA)
            if fired or test == "psi":
                rows.append({
                    "run_id": run_id, "checked_on": checked_on, "channel": "feature",
                    "subject": f, "test": test, "statistic": round(value, 5),
                    "threshold": threshold, "p_value": round(pv, 5) if pv is not None else None,
                    "fired": fired, "severity": severity_for(test, value, fired),
                    "window_start": checked_on - dt.timedelta(weeks=4), "window_end": checked_on,
                    "note": human_feature_note(f, test, value, pv, fired),
                })
    return rows


def human_feature_note(feature: str, test: str, value: float, p_value: float | None,
                       fired: bool) -> str:
    if not fired:
        return f"No actionable shift in feature {feature} ({test} {value:.3f})."
    if p_value is not None:
        return (f"Feature distribution for {feature} shifted ({test} statistic {value:.3f}, "
                f"p={p_value:.3f}); a change in what feeds the model.")
    return (f"Feature distribution for {feature} shifted (PSI {value:.3f}); "
            f"the inputs the model sees are no longer the inputs it trained on.")


def check_residual_drift(fc: pd.DataFrame, metrics: pd.DataFrame, run_id: str,
                         checked_on: dt.date) -> list[dict]:
    """Rolling MASE (2-week rule), Page–Hinkley, coverage gap — the relationship
    breaking, not just the inputs moving."""
    rows = []
    # rolling MASE
    if not fc.empty and "mase" in fc.columns:
        backtest_mase = None
        bt = metrics[(metrics["is_backtest"] == True) & (metrics["scope"] == "overall")]  # noqa: E712
        if not bt.empty:
            backtest_mase = float(bt["mase"].dropna().mean())
        rm, n = rolling_mase(fc, backtest_mase)
        if np.isfinite(rm) and backtest_mase is not None:
            threshold = backtest_mase * T.ROLLING_MASE_MULT
            fired = rm > threshold and n >= T.ROLLING_MASE_CONSECUTIVE
            rows.append({
                "run_id": run_id, "checked_on": checked_on, "channel": "residual",
                "subject": "overall", "test": "rolling_mase", "statistic": round(rm, 4),
                "threshold": round(threshold, 4), "p_value": None, "fired": fired,
                "severity": "critical" if fired else "info",
                "window_start": checked_on - dt.timedelta(weeks=T.ROLLING_MASE_WINDOW),
                "window_end": checked_on,
                "note": (f"Rolling MASE {rm:.2f} vs backtest {backtest_mase:.2f} "
                         f"since {checked_on - dt.timedelta(weeks=T.ROLLING_MASE_WINDOW)}"
                         if not fired else
                         f"Rolling MASE {rm:.2f} vs backtest {backtest_mase:.2f} — the "
                         f"relationship between features and prices has moved."),
            })
    # coverage gap
    gap, n = coverage_gap(metrics)
    if np.isfinite(gap):
        fired = gap > T.COVERAGE_GAP_MAX
        rows.append({
            "run_id": run_id, "checked_on": checked_on, "channel": "coverage",
            "subject": "overall", "test": "coverage_gap", "statistic": round(gap, 4),
            "threshold": T.COVERAGE_GAP_MAX, "p_value": None, "fired": fired,
            "severity": "warn" if fired else "info",
            "window_start": checked_on - dt.timedelta(weeks=T.COVERAGE_WINDOW),
            "window_end": checked_on,
            "note": (f"80% interval coverage is {0.80 + gap:.0%} — the intervals claim "
                     f"80% and deliver {0.80 + gap:.0%}; they are lying."
                     if fired else
                     f"80% interval coverage within tolerance over the last {n} weeks."),
        })
    return rows
