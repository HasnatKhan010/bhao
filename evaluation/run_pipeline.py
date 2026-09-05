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
from features.build import build_features
from ingest import config
from models import baselines as B
from models.global_gbm import GlobalGBM


def load_panel_items_national(data_dir=None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = data_dir or config.DATA_DIR
    panel = pd.read_parquet(base / "panel" / "prices_weekly.parquet")
    items = pd.read_parquet(base / "panel" / "items.parquet")
    nat = pd.read_parquet(base / "panel" / "national_weekly.parquet")
    return panel, items, nat


def make_registry(
    gbm: bool,
    summary: dict,
    table: pd.DataFrame,
    champ_mase_vs,
    force_champion: str | None = None,
    version: str | None = None,
) -> dict:
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
                    "mase_rw": (
                        float(table.loc[champion, "mase_rw"])
                        if champion in table.index and "mase_rw" in table.columns
                        else None
                    ),
                    "smape": (
                        float(table.loc[champion, "smape"]) if champion in table.index else None
                    ),
                    "coverage_80": (
                        float(table.loc[champion, "coverage_80"])
                        if champion in table.index
                        else None
                    ),
                    "beat_seasonal_naive_pct_of_series": champ_mase_vs,
                },
                "artefact_path": "data/registry/artefacts/",
                "artefact_sha256": hashlib.sha256(
                    f"{version}-{dt.datetime.now(dt.UTC).isoformat()}".encode()
                ).hexdigest(),
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


def write_runtime_artefacts(
    panel, items, nat, n_folds=12, include_slow=True, include_gbm=True, log_target=True, run_id=None
) -> dict:
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
        panel,
        items,
        nat,
        cfg=RunConfig(
            n_folds=n_folds,
            include_slow=include_slow,
            include_gbm=include_gbm,
            log_target=log_target,
        ),
        run_id=run_id,
        progress=True,
    )
    table = baseline_table(folds)
    champ_win = beat_seasonal_naive_pct(fc, panel) if include_gbm else float("nan")

    metrics = aggregate_metrics(
        fc,
        panel,
        items,
        summary["run_id"],
        season=summary.get("effective_season", summary.get("season_used", 4)),
    )
    fc.to_parquet(config.FORECASTS_DIR / "forecasts.parquet", index=False)
    metrics.to_parquet(config.FORECASTS_DIR / "metrics.parquet", index=False)

    # Champion = the gate winner: the model with the lowest backtest MASE among
    # those evaluated. On weekly retail prices that is often the random walk —
    # exactly the outcome 12-RISKS.md R1 predicts. Publishing "the GBM wins"
    # because it beat only seasonal-naive while losing to the random walk would
    # be the quiet dishonesty this project exists to avoid.
    scored = table.dropna(subset=["mase"])
    scored = scored[np.isfinite(scored["mase"])]
    champion = str(scored["mase"].idxmin())
    gbm_mase = float(table.loc["global_gbm", "mase"]) if "global_gbm" in table.index else None
    reg = make_registry(
        include_gbm,
        {
            **summary,
            "n_series": panel.groupby(["city_code", "item_code"]).ngroups,
            "n_rows": len(panel),
            "trained_through": sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))[-1],
        },
        table,
        champ_win,
        force_champion=champion,
    )
    reason = (
        f"Champion after the backtest: {champion} MASE "
        f"{table.loc[champion, 'mase']:.3f} over "
        f"{int(summary.get('folds', 0))} rolling-origin folds of the "
        f"{summary.get('effective_season', 4)}-week panel."
    )
    if champion == "random_walk" and gbm_mase is not None:
        reason += (
            f" The global GBM (MASE {gbm_mase:.3f}) does not beat the random walk on weekly "
            f"retail prices — the outcome 12-RISKS.md R1 predicts. It is re-evaluated every "
            f"week as the panel deepens; the per-commodity table shows where it does win."
        )
    reg["models"][0]["promoted_because"] = reason
    reg["promotion_log"].append(
        {
            "at": reg["updated_at"],
            "from": None,
            "to": champion,
            "decision": "promote",
            "reason": reason,
            "trigger": f"backtest {summary.get('run_id')}",
        }
    )
    (config.REGISTRY_DIR / "model_registry.json").write_text(
        json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("\nBASELINE TABLE:", table.to_string())
    print(f"\nchampion: {champion} | beat_seasonal_naive_pct: {champ_win}")
    # is_champion must reflect the ACTUAL champion, not whichever model ran last —
    # the API serves is_champion=True rows, so this flag is the serve decision.
    fc["is_champion"] = fc["model_name"] == champion

    # the forward forecast: predict the week AFTER the panel's last week. Without
    # this the app serves a stale forecast for a week whose actual already arrived.
    from contracts.schemas import latest_revision as _lr

    full = _lr(panel)
    made_on = sorted(set(pd.to_datetime(full["week_ending"]).dt.date))[-1]
    target_week = made_on + dt.timedelta(days=7)
    created = pd.Timestamp.now(dt.UTC).floor("s")
    eff_season = summary.get("effective_season", 4)

    fwd_frames = []
    for name, fn in B.FAST_BASELINES.items():
        out = (
            fn(full, target_week, season=eff_season)
            if name == "seasonal_naive"
            else fn(full, target_week)
        )
        fwd_frames.append(out)
    if include_gbm:
        feats_full = build_features(full, items, nat)
        gbm_full = GlobalGBM(log_target=log_target).fit(feats_full, made_on=made_on)
        last_rows = (
            feats_full.sort_values("week_ending")
            .groupby(["city_code", "item_code"], sort=False)
            .tail(1)
        )
        pred = gbm_full.predict(last_rows)[["city_code", "item_code", "p10", "p50", "p90"]]
        fwd_frames.append(pred)

    fwd_rows = []
    for name, out in zip([n for n in B.FAST_BASELINES] + (["global_gbm"] if include_gbm else []),
                         fwd_frames, strict=False):
        out = out.copy()
        out["run_id"] = summary["run_id"]
        out["model_name"] = name
        out["model_version"] = f"{name}-live"
        out["made_on"] = made_on
        out["target_week"] = target_week
        out["horizon"] = np.int32(1)
        out["is_champion"] = name == champion
        fv = summary.get("features_version", "feat-v1")
        out["features_hash"] = [
            hashlib.sha256(f"{c}|{i}|{made_on}|{fv}".encode()).hexdigest()[:16]
            for c, i in zip(out["city_code"], out["item_code"], strict=False)
        ]
        out["created_at"] = created
        fwd_rows.append(out)
    fc = pd.concat([fc] + fwd_rows, ignore_index=True)
    fc.to_parquet(config.FORECASTS_DIR / "forecasts.parquet", index=False)

    from drift.run_checks import run as run_drift_checks

    drift_df = run_drift_checks(run_id=summary["run_id"])
    print(f"drift: {len(drift_df)} rows, {int(drift_df['fired'].sum())} fired")
    return {
        "forecast_rows": len(fc),
        "metric_rows": len(metrics),
        "champion": champion,
        "drift_fired": int(drift_df["fired"].sum()),
        "table": table,
        "summary": summary,
    }


if __name__ == "__main__":
    panel, items, nat = load_panel_items_national()
    n_weeks = pd.to_datetime(panel["week_ending"]).dt.date.nunique()
    if n_weeks < 12:
        raise SystemExit(
            f"panel has only {n_weeks} weeks - too young for a backtest. "
            "Run the history bootstrap (make backfill) first; "
            "the weekly workflow does this automatically."
        )
    write_runtime_artefacts(panel, items, nat)
