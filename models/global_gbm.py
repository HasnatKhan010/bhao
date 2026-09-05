"""Global LightGBM over pooled series, three quantile heads (α = 0.1/0.5/0.9).

Why pooled rather than 867 per-series models: each series is too short for
per-series ML, but the dynamics are shared — onions in Lahore and onions in Multan
move together. Pooling also means one model to train, version and monitor.

- monotonicity enforced by sorting the three outputs per row (quantile crossing is
  normal and must be fixed, not hidden)
- recency sample weights, half-life ~26 weeks, so the model tracks the current regime
- log target tested against raw; the winner is recorded, not assumed
- CPU only; a full retrain must fit in a GH Actions runner in under 10 minutes
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from features.build import CATEGORICAL_COLS, feature_columns

QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
HALF_LIFE_WEEKS = 26

DEFAULT_PARAMS = dict(
    objective="quantile",
    num_leaves=63,
    learning_rate=0.05,
    n_estimators=400,
    min_child_samples=40,
    subsample=0.9,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    # GitHub Actions runners give 2-4 cores; local dev has more. Use what's there
    # but stay reproducible: LightGBM's histogram build is deterministic per thread
    # count, so the thread count is recorded in the registry alongside the metrics.
    n_jobs=min(8, os.cpu_count() or 2),
    verbose=-1,
)


def recency_weights(weeks: pd.Series, made_on) -> np.ndarray:
    age_weeks = (pd.Timestamp(made_on) - pd.to_datetime(weeks)).dt.days / 7.0
    return np.power(0.5, age_weeks / HALF_LIFE_WEEKS).to_numpy()


def _prep(X: pd.DataFrame, cat_cols: list[str], categories: dict | None = None):
    X = X.copy()
    cats = {}
    for c in cat_cols:
        if c not in X.columns:
            continue
        if categories and c in categories:
            X[c] = pd.Categorical(X[c].astype(str), categories=categories[c])
        else:
            X[c] = pd.Categorical(X[c].astype(str))
            cats[c] = list(X[c].cat.categories)
    for c in X.columns:
        if c not in cat_cols and X[c].dtype == bool:
            X[c] = X[c].astype(float)
        elif c not in cat_cols and X[c].dtype == object:
            X[c] = pd.to_numeric(X[c], errors="coerce")
    return X, (categories or cats)


class GlobalGBM:
    """Three quantile LightGBM heads over the pooled panel."""

    def __init__(self, params: dict | None = None, log_target: bool = True):
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.log_target = log_target
        self.models: dict[str, object] = {}
        self.feature_cols: list[str] = []
        self.categories: dict[str, list[str]] = {}
        self.gain: pd.Series | None = None

    def fit(self, feats: pd.DataFrame, made_on=None) -> GlobalGBM:
        import lightgbm as lgb

        # non-positive targets are parse artifacts (log undefined) — never train on them
        train = feats[feats["target"].notna() & (feats["target"] > 0)].copy()
        if train.empty:
            raise ValueError("no rows with a target: cannot fit")
        self.feature_cols = [c for c in feature_columns(train) if c != "target"]
        X, self.categories = _prep(train[self.feature_cols], CATEGORICAL_COLS)
        y = (
            np.log(train["target"].to_numpy(dtype=float))
            if self.log_target
            else train["target"].to_numpy(dtype=float)
        )
        w = recency_weights(train["week_ending"], made_on or train["week_ending"].max())

        for name, alpha in QUANTILES.items():
            model = lgb.LGBMRegressor(**{**self.params, "alpha": alpha})
            model.fit(
                X,
                y,
                sample_weight=w,
                categorical_feature=[c for c in CATEGORICAL_COLS if c in X.columns],
            )
            self.models[name] = model
        p50 = self.models["p50"]
        self.gain = pd.Series(p50.booster_.feature_importance("gain"), index=X.columns).sort_values(
            ascending=False
        )
        return self

    def predict(self, feats: pd.DataFrame) -> pd.DataFrame:
        X, _ = _prep(feats[self.feature_cols], CATEGORICAL_COLS, self.categories)
        preds = {}
        for name in QUANTILES:
            raw = self.models[name].predict(X)
            if self.log_target:
                # clip before exp: exp(12) ≈ Rs 163k is above any item in the basket
                # (the Rs-17,000 extreme logs to 9.7); a badly-fitted leaf must
                # produce a bounded price, not inf poisoning every pooled metric
                raw = np.clip(raw, -2, 12)
                preds[name] = np.exp(raw)
            else:
                preds[name] = raw
        out = pd.DataFrame(preds, index=feats.index)
        # enforce p10 <= p50 <= p90 by sorting the three outputs per row
        q = np.sort(out[["p10", "p50", "p90"]].to_numpy(dtype=float), axis=1)
        out[["p10", "p50", "p90"]] = np.round(q, 2)
        out["p10"] = out["p10"].clip(lower=0)
        out.insert(0, "city_code", feats["city_code"].to_numpy())
        out.insert(1, "item_code", feats["item_code"].to_numpy())
        return out

    def top_features(self, n: int = 20) -> list[str]:
        return [] if self.gain is None else list(self.gain.head(n).index)

    def save(self, path) -> None:
        import json
        import pickle
        from pathlib import Path

        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        with (p / "model.pkl").open("wb") as f:
            pickle.dump(
                {
                    "models": self.models,
                    "feature_cols": self.feature_cols,
                    "categories": self.categories,
                    "log_target": self.log_target,
                    "params": self.params,
                },
                f,
            )
        (p / "features.json").write_text(
            json.dumps(
                {"feature_cols": self.feature_cols, "top_gain": self.top_features(30)}, indent=2
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path) -> GlobalGBM:
        import pickle
        from pathlib import Path

        with (Path(path) / "model.pkl").open("rb") as f:
            blob = pickle.load(f)
        m = cls(params=blob["params"], log_target=blob["log_target"])
        m.models = blob["models"]
        m.feature_cols = blob["feature_cols"]
        m.categories = blob["categories"]
        return m
