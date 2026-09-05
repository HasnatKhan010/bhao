"""Run the drift checks against the current artefacts and write drift.parquet.

    python -m drift.run_checks

Reads data/forecasts/metrics.parquet (live + backtest scoring) and the panel;
writes data/forecasts/drift.parquet. Called by the weekly flow after scoring.
Feature drift uses the core feature set (lag_1, roll_mean_4, spread, pct_1,
vol_ratio_4_26); the top-20-by-gain restriction applies once model artefacts are
stored with the registry.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from drift import detect as D
from features.build import build_features
from ingest import config

CORE_FEATURES = ["lag_1", "roll_mean_4", "roll_mean_8", "spread", "pct_1", "vol_ratio_4_26"]


def run(run_id: str | None = None) -> pd.DataFrame:
    run_id = run_id or dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    checked_on = dt.date.today()
    config.ensure_dirs()

    metrics = pd.read_parquet(config.FORECASTS_DIR / "metrics.parquet")
    rows: list[dict] = []

    # --- residual channel: rolling MASE + coverage gap on the live champion ---
    live = metrics[(metrics["scope"] == "overall") & (~metrics["is_backtest"])]
    backtest = metrics[(metrics["scope"] == "overall") & (metrics["is_backtest"])]
    bt_mase = float(backtest["mase"].dropna().mean()) if len(backtest) else None

    champ = "random_walk"
    reg_path = config.REGISTRY_DIR / "model_registry.json"
    if reg_path.exists():
        import json

        champ = json.loads(reg_path.read_text(encoding="utf-8")).get("champion", champ)
    live_champ = live[live["model_name"] == champ].sort_values("target_week").tail(T_window())
    if len(live_champ):
        rm = float(live_champ["mase"].dropna().mean()) if len(live_champ) else float("nan")
        if np.isfinite(rm) and bt_mase:
            threshold = bt_mase * 1.25
            fired = rm > threshold and len(live_champ) >= 2
            rows.append(
                {
                    "run_id": run_id,
                    "checked_on": checked_on,
                    "channel": "residual",
                    "subject": "overall",
                    "test": "rolling_mase",
                    "statistic": round(rm, 4),
                    "threshold": round(threshold, 4),
                    "p_value": None,
                    "fired": fired,
                    "severity": "critical" if fired else "info",
                    "window_start": live_champ["target_week"].min(),
                    "window_end": live_champ["target_week"].max(),
                    "note": (
                        f"Live rolling MASE of the champion ({champ}) is {rm:.2f} "
                        f"against a backtest MASE of {bt_mase:.2f}."
                        if not fired
                        else f"Live rolling MASE {rm:.2f} vs backtest {bt_mase:.2f} "
                        f"over {len(live_champ)} weeks — the champion's relationship "
                        f"with prices has moved."
                    ),
                }
            )

    cov = live_champ["coverage_80"].dropna()
    if len(cov):
        gap = float(abs(cov.mean() - 0.80))
        fired = gap > 0.12
        rows.append(
            {
                "run_id": run_id,
                "checked_on": checked_on,
                "channel": "coverage",
                "subject": "overall",
                "test": "coverage_gap",
                "statistic": round(gap, 4),
                "threshold": 0.12,
                "p_value": None,
                "fired": fired,
                "severity": "warn" if fired else "info",
                "window_start": live_champ["target_week"].min(),
                "window_end": live_champ["target_week"].max(),
                "note": (
                    f"80% intervals delivered {cov.mean():.0%} coverage over the last "
                    f"{len(cov)} weeks — off by {gap:.0%}."
                    if fired
                    else f"80% interval coverage within tolerance over the last {len(cov)} weeks."
                ),
            }
        )

    # --- feature channel: PSI/KS on core features, training window vs last 4 weeks ---
    panel = pd.read_parquet(config.PANEL_DIR / "prices_weekly.parquet")
    items = pd.read_parquet(config.PANEL_DIR / "items.parquet")
    feats = build_features(panel, items)
    feats = feats.sort_values("week_ending")
    weeks = pd.to_datetime(feats["week_ending"]).dt.date.dropna().unique()
    if len(weeks) >= 12:
        cut = weeks[-5]
        wk = pd.to_datetime(feats["week_ending"]).dt.date
        ref = feats[wk < cut]
        cur = feats[wk >= cut]
        rows.extend(D.check_feature_drift(ref, cur, CORE_FEATURES, run_id, checked_on))

    df = pd.DataFrame(rows)
    from contracts.schemas import validate_drift

    if not df.empty:
        df = validate_drift(df)
    df.to_parquet(config.FORECASTS_DIR / "drift.parquet", index=False)
    fired = int(df["fired"].sum()) if len(df) else 0
    print(f"drift.parquet: {len(df)} rows, {fired} fired")
    return df


def T_window() -> int:
    from drift import thresholds as T

    return T.ROLLING_MASE_WINDOW


if __name__ == "__main__":
    run()
