"""Model-track tests: baselines, metrics, quantile monotonicity, feature discipline.

Fast by construction — a tiny synthetic panel, not the 132k-row fixture set. The
fixture-scale run lives in the Phase 2 gate, not in the unit suite.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from evaluation import metrics as M
from evaluation.report import RunConfig, baseline_table, fold_denominators, run_backtest
from features.build import build_features, feature_columns
from models import baselines as B
from models.global_gbm import GlobalGBM

WEEKS = 80


def _panel(n_items: int = 3, n_cities: int = 2, weeks: int = WEEKS) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = []
    start = dt.date(2025, 1, 2)  # a Thursday
    for ci in range(n_cities):
        city = f"{ci + 1:02d}"
        for ii in range(n_items):
            item = f"{ii + 1:03d}"
            base = 100.0 * (ii + 1)
            path = base * np.exp(np.cumsum(rng.normal(0.001, 0.02, weeks)))
            for w in range(weeks):
                week = start + dt.timedelta(weeks=w)
                avg = round(float(path[w]), 2)
                rows.append(
                    {
                        "week_ending": week,
                        "city_code": city,
                        "city_en": f"City{ci}",
                        "city_ur": "شہر",
                        "item_code": item,
                        "item_en": f"Item{ii}",
                        "item_ur": "چیز",
                        "unit_raw": "1 Kg",
                        "unit_norm": "kg",
                        "qty_norm": 1.0,
                        "price_min": round(avg * 0.97, 2),
                        "price_avg": avg,
                        "price_max": round(avg * 1.03, 2),
                        "price_per_unit": avg,
                        "source": "pbs_spi_annex",
                        "source_url": "https://x.example/a.xlsx",
                        "ingested_at": pd.Timestamp(week + dt.timedelta(days=2), tz="UTC"),
                        "revision": np.int32(0),
                    }
                )
    return pd.DataFrame(rows).astype(
        {"qty_norm": "float64", "revision": "int32", "ingested_at": "datetime64[us, UTC]"}
    )


def _items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "item_code": f"{i + 1:03d}",
                "item_en": f"Item{i}",
                "item_ur": "چیز",
                "unit_raw": "1 Kg",
                "unit_norm": "kg",
                "qty_norm": 1.0,
                "category": ["vegetables", "grains", "fuel_energy"][i % 3],
                "spi_weight": 1.0,
                "is_food": i % 3 != 2,
                "is_administered": i % 3 == 2,
                "pbs_aliases": [f"Item{i}"],
                "first_seen": dt.date(2025, 1, 2),
                "last_seen": dt.date(2026, 1, 1),
                "notes": None,
            }
            for i in range(3)
        ]
    )


@pytest.fixture(scope="module")
def panel():
    return _panel()


@pytest.fixture(scope="module")
def items():
    return _items()


class TestBaselines:
    def test_all_six_exist(self):
        assert set(B.BASELINES) == {
            "random_walk",
            "seasonal_naive",
            "drift",
            "seasonal_naive_ma",
            "ets",
            "arima",
        }

    @pytest.mark.parametrize(
        "name", ["random_walk", "seasonal_naive", "drift", "seasonal_naive_ma", "ets"]
    )
    def test_produces_one_row_per_series_with_monotone_quantiles(self, panel, name):
        out = B.BASELINES[name](panel, dt.date(2026, 7, 16))
        assert len(out) == 6  # 2 cities x 3 items
        ok = out.dropna(subset=["p10", "p50", "p90"])
        assert (ok["p10"] <= ok["p50"]).all()
        assert (ok["p50"] <= ok["p90"]).all()
        assert (ok["p10"] >= 0).all()

    def test_random_walk_is_last_value(self, panel):
        out = B.random_walk(panel)
        last = (
            panel.sort_values("week_ending")
            .groupby(["city_code", "item_code"])
            .tail(1)
            .set_index(["city_code", "item_code"])["price_avg"]
        )
        got = out.set_index(["city_code", "item_code"])["p50"]
        assert np.allclose(got.sort_index().to_numpy(), last.sort_index().to_numpy(), atol=0.01)

    def test_seasonal_naive_uses_the_lagged_week(self, panel):
        target = pd.to_datetime(panel["week_ending"]).max().date() + dt.timedelta(weeks=1)
        out = B.seasonal_naive(panel, target, season=52)
        want_week = target - dt.timedelta(weeks=52)
        truth = panel[pd.to_datetime(panel["week_ending"]).dt.date == want_week]
        truth = truth.set_index(["city_code", "item_code"])["price_avg"]
        got = out.set_index(["city_code", "item_code"])["p50"].dropna()
        assert len(got) == len(truth)
        assert np.allclose(got.sort_index().to_numpy(), truth.sort_index().to_numpy(), atol=0.01)

    def test_short_series_yields_null_not_zero(self):
        short = _panel(n_items=1, n_cities=1, weeks=3)
        out = B.seasonal_naive(short, dt.date(2025, 2, 6), season=52)
        assert out["p50"].isna().all(), "insufficient history must be null, never 0"


class TestMetrics:
    def test_mase_denominator_is_the_baseline(self):
        # a perfect seasonal-naive forecast scores MASE 1.0 against its own denominator
        y = pd.Series([100.0, 102, 104, 106, 108, 110])
        den = M.rw_denominator(y)
        assert den == pytest.approx(2.0)
        keys = pd.DataFrame({"city_code": ["01"], "item_code": ["001"]})
        dens = pd.Series(
            [den],
            index=pd.MultiIndex.from_tuples([("01", "001")], names=["city_code", "item_code"]),
        )
        mase = M.pooled_mase(keys, np.array([112.0]), np.array([110.0]), dens)
        assert mase == pytest.approx(1.0)

    def test_snaive_falls_back_to_season_4_on_short_series(self):
        s = pd.Series(np.arange(20, dtype=float))
        assert M.denominator_season(s, 52) == 4
        assert np.isfinite(M.snaive_denominator(s, 52))

    def test_coverage_and_pinball(self):
        y = np.array([100.0, 110.0, 90.0, 105.0])
        p10 = np.array([95.0, 95.0, 95.0, 95.0])
        p90 = np.array([115.0, 115.0, 115.0, 115.0])
        assert M.coverage_80(y, p10, p90) == 0.75
        assert M.pinball(y, np.array([100.0] * 4), 0.5) >= 0

    def test_bias_sign_is_over_forecasting_positive(self):
        y = np.array([100.0, 100.0])
        over = np.array([110.0, 110.0])
        assert M.bias(y, over) == pytest.approx(10.0)

    def test_smape_is_symmetric_and_bounded(self):
        assert M.smape(np.array([100.0]), np.array([110.0])) == pytest.approx(
            M.smape(np.array([110.0]), np.array([100.0]))
        )


class TestFoldDenominators:
    def test_uses_only_the_folds_training_portion(self, panel):
        from evaluation.backtest import make_folds

        folds = make_folds(panel, n_folds=4)
        sn_early, rw_early, _ = fold_denominators(folds[0].train)
        sn_late, rw_late, _ = fold_denominators(folds[-1].train)
        # later folds see more data, so the denominators genuinely differ
        assert not np.allclose(rw_early.to_numpy(), rw_late.to_numpy())
        assert len(rw_early) == 6


class TestFeatureDiscipline:
    def test_no_feature_uses_the_target_week(self, panel, items):
        feats = build_features(panel, items)
        f = feats.sort_values(["city_code", "item_code", "week_ending"], kind="mergesort")
        nxt = f.groupby(["city_code", "item_code"])["price_avg"].shift(-1)
        assert np.allclose(f["target"].to_numpy(float), nxt.to_numpy(float), equal_nan=True)
        prev = f.groupby(["city_code", "item_code"])["price_avg"].shift(1)
        assert np.allclose(f["lag_1"].to_numpy(float), prev.to_numpy(float), equal_nan=True)

    def test_cross_sectional_features_are_lagged(self, panel, items):
        feats = build_features(panel, items).sort_values(
            ["city_code", "item_code", "week_ending"], kind="mergesort"
        )
        one = feats[(feats["city_code"] == "01") & (feats["item_code"] == "001")].reset_index(
            drop=True
        )
        # xs_item_mean_lag1 at week t must equal the cross-city mean at week t-1
        wk = one["week_dt"].iloc[10]
        prev_wk = wk - pd.Timedelta(weeks=1)
        prev_mean = feats[(feats["week_dt"] == prev_wk) & (feats["item_code"] == "001")][
            "price_avg"
        ].mean()
        assert one["xs_item_mean_lag1"].iloc[10] == pytest.approx(prev_mean)

    def test_hijri_flags_present_and_binary(self, panel, items):
        feats = build_features(panel, items)
        for c in ("ramadan", "eid_fitr", "eid_adha"):
            assert c in feats.columns
            assert set(feats[c].unique()) <= {0.0, 1.0}

    def test_spread_feature_exists(self, panel, items):
        feats = build_features(panel, items)
        assert "spread" in feats.columns and "spread_trend" in feats.columns
        assert feats["spread"].dropna().between(0, 1).all()

    def test_feature_columns_exclude_target_and_raw_price(self, panel, items):
        cols = feature_columns(build_features(panel, items))
        for banned in (
            "target",
            "target_log",
            "price_avg",
            "price_min",
            "price_max",
            "week_ending",
            "ingested_at",
            "revision",
        ):
            assert banned not in cols


class TestGlobalGBM:
    def test_fits_and_enforces_monotone_quantiles(self, panel, items):
        feats = build_features(panel, items)
        gbm = GlobalGBM(log_target=True).fit(
            feats, made_on=pd.to_datetime(feats["week_ending"]).max().date()
        )
        last = feats.sort_values("week_ending").groupby(["city_code", "item_code"]).tail(1)
        out = gbm.predict(last)
        assert len(out) == 6
        assert (out["p10"] <= out["p50"]).all() and (out["p50"] <= out["p90"]).all()
        assert (out["p10"] >= 0).all()
        assert len(gbm.top_features(10)) > 0

    def test_roundtrip_save_load(self, panel, items, tmp_path):
        feats = build_features(panel, items)
        gbm = GlobalGBM().fit(feats)
        gbm.save(tmp_path / "gbm")
        again = GlobalGBM.load(tmp_path / "gbm")
        last = feats.sort_values("week_ending").groupby(["city_code", "item_code"]).tail(1)
        a = gbm.predict(last)["p50"].to_numpy()
        b = again.predict(last)["p50"].to_numpy()
        assert np.allclose(a, b)


class TestBacktestRun:
    def test_runs_and_reports_both_denominators(self, panel, items):
        fc, folds, summary = run_backtest(
            panel,
            items,
            None,
            cfg=RunConfig(n_folds=3, include_slow=False, include_gbm=False),
            run_id="test-run",
            progress=False,
        )
        assert summary["folds"] == 3
        assert not fc.empty
        table = baseline_table(folds)
        assert "mase" in table.columns and "mase_rw" in table.columns
        # baselines are always written so the scorecard can show what was beaten
        assert {"random_walk", "seasonal_naive"} <= set(fc["model_name"])

    def test_forecast_frame_satisfies_contract_2(self, panel, items):
        from contracts.schemas import validate_frame

        fc, _, _ = run_backtest(
            panel,
            items,
            None,
            cfg=RunConfig(n_folds=2, include_slow=False, include_gbm=False),
            run_id="test-run-2",
            progress=False,
        )
        fc = fc.dropna(subset=["p50"])
        validate_frame(fc, "forecasts")

    def test_exactly_one_champion_per_series_per_target_week(self, panel, items):
        fc, _, _ = run_backtest(
            panel,
            items,
            None,
            cfg=RunConfig(n_folds=2, include_slow=False, include_gbm=False),
            run_id="test-run-3",
            progress=False,
        )
        champ = fc[fc["is_champion"]]
        counts = champ.groupby(["city_code", "item_code", "target_week"]).size()
        assert (counts == 1).all()
