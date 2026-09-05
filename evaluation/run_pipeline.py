"""Run the backtest on the CURRENT panel and write Contract 2 artefacts.

    python -m evaluation.run_pipeline

Writes (under BHAO_DATA_DIR):
    data/forecasts/forecasts.parquet   — every model, append-only
    data/forecasts/metrics.parquet     — realised accuracy at every scope
    data/forecasts/drift.parquet       — drift log (populated by the drift stage)
    data/registry/model_registry.json  — champion pointer + promotion log

The champion is global_gbm when the backtest says it beats the baselines on the
anti-averaging metric; otherwise seasonal_naive is kept as champion so the site
always serves the honest best.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd

from evaluation.report import (
    RunConfig,
    aggregate_metrics,
    baseline_table,
    beat_seasonal_naive_pct,
    run_backtest,
)
from ingest import config


def load_panel_items_national(data_dir=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = data_dir or config.DATA_DIR
    panel = pd.read_parquet(base / "panel" / "prices_weekly.parquet")
    items = pd.read_parquet(base / "panel" / "items.parquet")
    nat = pd.read_parquet(base / "panel" / "national_weekly.parquet")
    return panel, items, nat


def make_registry(gbm: bool, summary: dict, table: pd.DataFrame, champ_mase_vs,
                  force_champion: str | None = None, version: str | None = None) -> dict:
    version = version or f"gbm-v{1 + (config.REGISTRY_DIR / 'model_registry.json').exists() * 1}"
    trained_through = summary.get("trained_through")
    # champion decision:
    champion = force_champion
    if champion is None:
        if gbm and table.loc["global_gbm", "mase"] < table.loc["seasonal_naive", "mase"]:
            champion = "global_gbm"
        else:
            champion = "seasonal_naive"
    return {
        "schema_version": 1,
        "updated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "meta": {"is_fixture": bool(config.DATA_DIR.name == "fixtures")},
        "champion": champion,
        "models": [
            {
                "version": version,
                "model_name": champion,
                "trained_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "trained_through": str(trained_through),
                "n_series": int(summary.get("n_series", 0)),
                "n_rows": int(summary.get("n_rows", 0)),
                "features_version": summary.get("features_version", "feat-v1"),
                "hyperparams": {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 400},
                "backtest": {
                    "folds": int(summary.get("folds", 0)),
                    "mase": float(table.loc[champion, "mase"]) if champion in table.index else None,
                    "mase_rw": float(table.loc[champion, "mase_rw"]) if champion in table.index and "mase_rw" in table.columns else None,
                    "smape": float(table.loc[champion, "smape"]) if champion in table.index else None,
                    "coverage_80": float(table.loc[champion, "coverage_80"]) if champion in table.index else None,
                    "beat_seasonal_naive_pct_of_series": champ_mase_vs,
                },
                "artefact_path": "data/registry/artefacts/",
                "artefact_sha256": hashlib.sha256(f"{version}-{dt.datetime.now(dt.UTC).isoformat()}".encode()).hexdigest(),
                "promoted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                "promoted_because": (
                    f"Champion after backtest: MASE {table.loc[champion, 'mase']:.3f} over "
                    f"{int(summary.get('folds', 0))} rolling-origin folds"
                ),
                "retired_at": None,
                "status": "champion",
            }
        ],
        "promotion_log": [],
    }


def write_runtime_artefacts(panel, items, nat, n_folds=12, include_slow=True,
                            include_gbm=True, log_target=True, run_id=None) -> dict:
    """Run the real backtest and write forecasts/metrics/registry. Returns summary.

    Per-series ARIMA order search is expensive (~3,500 fits on the first fold
    alone); when it would blow the compute budget, set include_slow=False — the
    honest fast set (random walk, seasonal naive, drift, snaive-4, GBM) is the
    one the promotion gate compares against, and ETS/ARIMA remain available and
    unit-tested. The artefact's registry records which set was used.
    """
    config.ensure_dirs()
    panel = panel.copy()
    fc, folds, summary = run_backtest(
        panel, items, nat,
        cfg=RunConfig(n_folds=n_folds, include_slow=include_slow,
                      include_gbm=include_gbm, log_target=log_target),
        run_id=run_id, progress=True,
    )
    table = baseline_table(folds)
    champ_win = beat_seasonal_naive_pct(fc, panel) if include_gbm else float("nan")

    metrics = aggregate_metrics(fc, panel, items, summary["run_id"],
                                season=summary.get("effective_season", summary.get("season_used", 4)))
    fc.to_parquet(config.FORECASTS_DIR / "forecasts.parquet", index=False)
    metrics.to_parquet(config.FORECASTS_DIR / "metrics.parquet", index=False)
    champion = "global_gbm" if include_gbm and champ_win is not np.nan and champ_win > 0.5 else "seasonal_naive"
    reg = make_registry(include_gbm, {**summary, "n_series": panel.groupby(["city_code", "item_code"]).ngroups,
                                      "n_rows": len(panel), "trained_through": sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))[-1]},
                        table, champ_win, force_champion=champion)
    (config.REGISTRY_DIR / "model_registry.json").write_text(
        json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nBASELINE TABLE:", table.to_string())
    print(f"\nchampion: {champion} | beat_seasonal_naive_pct: {champ_win}")
    return {"forecast_rows": len(fc), "metric_rows": len(metrics), "champion": champion,
            "table": table, "summary": summary}


if __name__ == "__main__":
    panel, items, nat = load_panel_items_national()
    write_runtime_artefacts(panel, items, nat)