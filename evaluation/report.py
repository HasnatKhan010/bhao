"""The backtest runner: rolling-origin folds × models → forecasts + metrics.

Frozen protocol (10-EVALUATION.md). Every fold:
  train = as_of(panel, made_on)   # revision-aware, nothing after made_on
  features built on that training view only
  MASE denominator = in-sample one-step seasonal-naive MAE on THAT fold's
  training portion, per series — never the full series, never the test window.

Reports at every Contract-2 scope, plus beat_seasonal_naive_pct_of_series.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from evaluation import metrics as M
from evaluation.backtest import make_folds
from features.build import FEATURES_VERSION, build_features
from models import baselines as B
from models.global_gbm import GlobalGBM

KEYS = ["city_code", "item_code"]


@dataclass
class RunConfig:
    n_folds: int = 12
    include_slow: bool = True  # ets + arima
    include_gbm: bool = True
    log_target: bool = True
    season: int = 52
    min_train_weeks: int = 8  # per R3: with a short panel, K is reduced, not faked


def fold_denominators(train: pd.DataFrame, season: int = 52) -> tuple[pd.Series, pd.Series, int]:
    """Per-series in-sample one-step MAE denominators on THIS fold's training data.

    Returns (seasonal_naive_den, random_walk_den, season_actually_used). Both are
    reported: on a panel carrying ~9% headline YoY inflation the lag-52 denominator
    is inflated by drift, so seasonal-naive MASE flatters every model. The lag-1
    (random-walk) denominator is the honest bar.
    """
    sn: dict[tuple[str, str], float] = {}
    rw: dict[tuple[str, str], float] = {}
    used_season = season
    for key, sub in train.sort_values("week_ending").groupby(KEYS, sort=False):
        s = sub["price_avg"]
        sn[key] = M.snaive_denominator(s, season)
        rw[key] = M.rw_denominator(s)
        used_season = min(used_season, M.denominator_season(s, season))
    idx = pd.MultiIndex.from_tuples(sn.keys(), names=KEYS)
    return (
        pd.Series(list(sn.values()), index=idx, name="den"),
        pd.Series(list(rw.values()), index=idx, name="den"),
        used_season,
    )


def _score(
    keys: pd.DataFrame,
    actual: np.ndarray,
    p10: np.ndarray,
    p50: np.ndarray,
    p90: np.ndarray,
    dens: pd.Series,
    dens_rw: pd.Series | None = None,
) -> dict:
    out = {
        "n_obs": int((np.isfinite(actual) & np.isfinite(p50)).sum()),
        "mase": M.pooled_mase(keys, actual, p50, dens),
        "smape": M.smape(actual, p50),
        "mae": M.mae(actual, p50),
        "rmse": M.rmse(actual, p50),
        "pinball_10": M.pinball(actual, p10, 0.1),
        "pinball_50": M.pinball(actual, p50, 0.5),
        "pinball_90": M.pinball(actual, p90, 0.9),
        "coverage_80": M.coverage_80(actual, p10, p90),
        "bias": M.bias(actual, p50),
    }
    if dens_rw is not None:
        # additive extra column: allowed by Contract 1 conventions, ignored by consumers
        out["mase_rw"] = M.pooled_mase(keys, actual, p50, dens_rw)
    return out


def run_backtest(
    panel: pd.DataFrame,
    items: pd.DataFrame | None = None,
    national: pd.DataFrame | None = None,
    cfg: RunConfig | None = None,
    run_id: str | None = None,
    progress: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """→ (forecasts, metrics, summary). Forecasts carry every model, per Contract 2
    invariant 4 (baselines are always written so the scorecard can show what was beaten).
    """
    cfg = cfg or RunConfig()
    run_id = run_id or dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    folds = make_folds(panel, n_folds=cfg.n_folds, min_train_weeks=cfg.min_train_weeks)
    created = pd.Timestamp.now(dt.UTC).floor("s")

    # R3 (12-RISKS.md): lag-52 needs ~2 years of panel. A shorter panel is a fact,
    # not a scandal — the methodology says which season was actually used.
    n_weeks = pd.to_datetime(panel["week_ending"]).dt.date.nunique()
    effective_season = cfg.season if n_weeks >= 2 * cfg.season else 4

    model_fns = dict(B.FAST_BASELINES)
    if cfg.include_slow:
        model_fns["ets"] = B.ets
        model_fns["arima"] = B.arima

    arima_cache: dict = {}
    fc_rows: list[pd.DataFrame] = []
    per_fold: list[dict] = []
    season_used = cfg.season

    for fold in folds:
        train, ev = fold.train, fold.eval
        if ev.empty:
            continue
        dens, dens_rw, used = fold_denominators(train, effective_season)
        season_used = min(season_used, used)

        actual = ev[["city_code", "item_code", "price_avg"]].rename(columns={"price_avg": "actual"})

        preds: dict[str, pd.DataFrame] = {}
        for name, fn in model_fns.items():
            if name == "arima":
                out = fn(train, fold.target_week, order_cache=arima_cache)
            elif name in ("seasonal_naive",):
                out = fn(train, fold.target_week, season=effective_season)
            else:
                out = fn(train, fold.target_week)
            preds[name] = out

        if cfg.include_gbm:
            feats = build_features(train, items, national)
            gbm = GlobalGBM(log_target=cfg.log_target).fit(feats, made_on=fold.made_on)
            # predict from the LAST row of each series (made_on's features)
            last = feats.sort_values("week_ending").groupby(KEYS, sort=False).tail(1).copy()
            gbm_out = gbm.predict(last)
            preds["global_gbm"] = gbm_out[["city_code", "item_code", "p10", "p50", "p90"]]

        for name, out in preds.items():
            if out.empty:
                continue
            merged = out.merge(actual, on=KEYS, how="inner")
            merged = merged[merged["actual"].notna()]
            if merged.empty:
                continue
            keys = merged[KEYS]
            row = _score(
                keys,
                merged["actual"].to_numpy(float),
                merged["p10"].to_numpy(float),
                merged["p50"].to_numpy(float),
                merged["p90"].to_numpy(float),
                dens,
                dens_rw,
            )
            row.update(
                {
                    "fold": fold.index,
                    "model_name": name,
                    "made_on": fold.made_on,
                    "target_week": fold.target_week,
                }
            )
            per_fold.append(row)

            fc = out.copy()
            fc["run_id"] = run_id
            fc["model_name"] = name
            fc["model_version"] = f"{name}-bt"
            fc["made_on"] = fold.made_on
            fc["target_week"] = fold.target_week
            fc["horizon"] = np.int32(1)
            fc["is_champion"] = name == ("global_gbm" if cfg.include_gbm else "seasonal_naive")
            fc["features_hash"] = [
                hashlib.sha256(f"{c}|{i}|{fold.made_on}|{FEATURES_VERSION}".encode()).hexdigest()[
                    :16
                ]
                for c, i in zip(fc["city_code"], fc["item_code"], strict=False)
            ]
            fc["created_at"] = created
            fc_rows.append(fc)

        if progress:
            best = min(
                (r for r in per_fold if r["fold"] == fold.index),
                key=lambda r: (r["mase"] if np.isfinite(r["mase"]) else np.inf),
            )
            print(
                f"  fold {fold.index:>2} made_on={fold.made_on} best={best['model_name']} "
                f"MASE={best['mase']:.3f}",
                flush=True,
            )

    forecasts = pd.concat(fc_rows, ignore_index=True) if fc_rows else pd.DataFrame()
    fold_df = pd.DataFrame(per_fold)
    summary = {
        "run_id": run_id,
        "folds": int(fold_df["fold"].nunique()) if len(fold_df) else 0,
        "season_used": season_used,
        "effective_season": effective_season,
        "features_version": FEATURES_VERSION,
    }
    return forecasts, fold_df, summary


def aggregate_metrics(
    forecasts: pd.DataFrame,
    panel: pd.DataFrame,
    items: pd.DataFrame | None,
    run_id: str,
    season: int = 52,
    is_backtest: bool = True,
) -> pd.DataFrame:
    """Contract-2 metrics.parquet rows at every scope, per target_week per model."""
    from contracts.schemas import latest_revision

    truth = latest_revision(panel)[["week_ending", "city_code", "item_code", "price_avg"]]
    truth = truth.rename(columns={"week_ending": "target_week", "price_avg": "actual"})
    df = forecasts.merge(truth, on=["target_week", "city_code", "item_code"], how="inner")
    df = df[df["actual"].notna() & df["p50"].notna()]
    if df.empty:
        return pd.DataFrame()

    cat = (
        items.set_index("item_code")["category"]
        if items is not None and len(items)
        else pd.Series(dtype="object")
    )
    admin = (
        items.set_index("item_code")["is_administered"]
        if items is not None and len(items)
        else pd.Series(dtype=bool)
    )
    df["category"] = df["item_code"].map(cat).fillna("other")
    df["is_administered"] = df["item_code"].map(admin).fillna(False)

    # denominators from the whole panel history up to each target_week's made_on
    rows: list[dict] = []
    evaluated_on = dt.date.today()

    for (target_week, model_name), sub in df.groupby(["target_week", "model_name"], sort=True):
        made_on = target_week - dt.timedelta(weeks=1)
        train = panel[pd.to_datetime(panel["week_ending"]).dt.date <= made_on]
        dens, dens_rw, _ = fold_denominators(latest_revision(train), season)
        version = sub["model_version"].iloc[0]

        ctx = (dens, dens_rw, target_week, model_name, version)

        def emit(scope, part, city=None, item=None, *, _ctx=ctx):
            if part.empty:
                return
            _dens, _dens_rw, _tw, _mn, _v = _ctx  # binds the loop iteration explicitly
            s = _score(
                part[KEYS],
                part["actual"].to_numpy(float),
                part["p10"].to_numpy(float),
                part["p50"].to_numpy(float),
                part["p90"].to_numpy(float),
                _dens,
                _dens_rw,
            )
            rows.append(
                {
                    "run_id": run_id,
                    "evaluated_on": evaluated_on,
                    "target_week": _tw,
                    "model_name": _mn,
                    "model_version": _v,
                    "scope": scope,
                    "city_code": city,
                    "item_code": item,
                    "is_backtest": is_backtest,
                    **{
                        k: (None if isinstance(v, float) and not np.isfinite(v) else v)
                        for k, v in s.items()
                        if k != "n_obs"
                    },
                    "n_obs": np.int32(s["n_obs"]),
                }
            )

        emit("overall", sub)
        for city, part in sub.groupby("city_code"):
            emit("city", part, city=city)
        for item, part in sub.groupby("item_code"):
            emit("item", part, item=item)
        for _cat, part in sub.groupby("category"):
            emit("category", part)
        emit("administered", sub[sub["is_administered"]])

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["n_obs"] = out["n_obs"].astype("int32")
    for c in (
        "mase",
        "mase_rw",
        "smape",
        "mae",
        "rmse",
        "pinball_10",
        "pinball_50",
        "pinball_90",
        "coverage_80",
        "bias",
    ):
        if c in out.columns:
            out[c] = out[c].astype("float64")
    return out


def beat_seasonal_naive_pct(
    forecasts: pd.DataFrame, panel: pd.DataFrame, model_name: str = "global_gbm"
) -> float:
    """Fraction of series where `model_name` beats seasonal_naive on MAE.

    The anti-averaging metric: an overall MASE of 0.78 driven by 20 series while
    losing on 500 is a bad model with a flattering average.
    """
    from contracts.schemas import latest_revision

    truth = latest_revision(panel)[["week_ending", "city_code", "item_code", "price_avg"]]
    truth = truth.rename(columns={"week_ending": "target_week", "price_avg": "actual"})
    df = forecasts.merge(truth, on=["target_week", "city_code", "item_code"], how="inner")
    df = df[df["actual"].notna() & df["p50"].notna()]
    a = df[df["model_name"] == model_name]
    b = df[df["model_name"] == "seasonal_naive"]
    if a.empty or b.empty:
        return float("nan")
    return M.beat_pct(
        a[KEYS], (a["actual"] - a["p50"]).to_numpy(), b[KEYS], (b["actual"] - b["p50"]).to_numpy()
    )


def baseline_table(fold_df: pd.DataFrame) -> pd.DataFrame:
    """The table B publishes to STATUS.md before training anything.

    `mase` uses the seasonal-naive (lag-52) denominator that 10-EVALUATION.md fixes
    as the headline; `mase_rw` uses lag-1. Report both — on this panel the lag-52
    denominator is inflated by ~9% headline YoY inflation, so a random walk alone
    scores MASE ≈ 0.15 against it, and that number is about the inflation, not the
    model.
    """
    if fold_df.empty:
        return fold_df
    aggs = dict(
        folds=("fold", "nunique"),
        mase=("mase", "mean"),
        mase_sd=("mase", "std"),
        smape=("smape", "mean"),
        mae=("mae", "mean"),
        coverage_80=("coverage_80", "mean"),
        bias=("bias", "mean"),
        n_obs=("n_obs", "sum"),
    )
    if "mase_rw" in fold_df.columns:
        aggs["mase_rw"] = ("mase_rw", "mean")
    return fold_df.groupby("model_name").agg(**aggs).sort_values("mase").round(4)
