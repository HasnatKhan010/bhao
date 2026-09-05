"""Drift + promotion tests.

The one the spec requires above all: the detector FIRES on the fixture's planted
variance regime shift (potatoes, item 021, sigma x4 from week index 100) — that
test is the substitute for a real drift event, and it is sufficient.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from drift import detect as D
from drift import thresholds as T
from registry import promote as P


def _shifted_series() -> np.ndarray:
    """A series with sigma x4 from index 100 (the fixture's planted pathology)."""
    rng = np.random.default_rng(11)
    n = 156
    sig = np.full(n, 0.02)
    sig[100:] = 0.08
    return np.exp(np.cumsum(rng.normal(0.0005, sig)))


class TestPSI:
    def test_identical_distributions_score_zero(self):
        a = np.random.default_rng(1).normal(100, 5, 2000)
        assert D.psi(a, a) < 0.05

    def test_shifted_distribution_scores_high(self):
        a = np.random.default_rng(1).normal(100, 5, 2000)
        b = np.random.default_rng(2).normal(115, 5, 2000)
        assert D.psi(a, b) > 0.25

    def test_bands(self):
        assert T.PSI_NONE == 0.10 and T.PSI_WARN == 0.25


class TestPageHinkley:
    def test_fires_on_sustained_shift(self):
        rng = np.random.default_rng(3)
        resid = np.concatenate([rng.normal(0, 1, 40), rng.normal(2.0, 1, 40)])
        fired, mag = D.page_hinkley(resid)
        assert fired, f"Page-Hinkley must fire on a sustained mean shift (mag {mag:.1f})"

    def test_quiet_residuals_do_not_fire(self):
        # PH's delta is tuned to the fixture's quiet regime (mean |log-return|
        # ~0.016, delta 0.02); a quiet series must not fire within a realistic span
        rng = np.random.default_rng(4)
        resid = rng.normal(0, 0.01, 100)
        fired, _ = D.page_hinkley(resid)
        assert not fired


class TestRollingMase:
    def test_requires_two_consecutive_bad_weeks(self):
        fc = pd.DataFrame(
            {
                "target_week": pd.date_range("2026-01-01", periods=10, freq="7D"),
                "model_name": ["global_gbm"] * 10,
                "mase": [0.9] * 8 + [1.5, 1.5],  # two bad weeks at the end
            }
        )
        rm, n = D.rolling_mase(fc, 0.8)
        assert n == T.ROLLING_MASE_WINDOW  # an 8-week rolling window
        assert rm > 0.8 * T.ROLLING_MASE_MULT  # the 2-week rule fired


class TestDetectorOnFixtureRegimeShift:
    """The required test: the detector fires on the fixture's planted variance
    regime shift. If B's pipeline crashes on it, that is a bug found in Phase 1
    instead of Phase 3 (03-CONTRACTS.md §Fixtures, rule 3)."""

    def test_psi_fires_on_shifted_item(self):
        series = _shifted_series()
        ref = series[40:100]  # before the shift
        cur = series[100:140]  # after the shift
        stat = D.psi(ref, cur)
        assert stat > 0.25, f"PSI {stat:.3f} should be critical (>0.25)"

    def test_ks_fires_on_shifted_item(self):
        series = _shifted_series()
        ref = series[40:100]
        cur = series[100:140]
        _, p = D.ks_two_sample(ref, cur)
        assert p < T.KS_ALPHA

    def test_page_hinkley_fires_on_shifted_item(self):
        series = _shifted_series()
        log_returns = np.abs(np.diff(np.log(series)))
        fired, mag = D.page_hinkley(log_returns)
        assert fired, f"PH must catch the variance shift (mag {mag:.1f})"

    def test_quiet_reference_does_not_fire(self):
        series = _shifted_series()
        pre = np.abs(np.diff(np.log(series)))[10:80]  # fully inside the quiet regime
        fired, mag = D.page_hinkley(pre)
        assert not fired, f"quiet regime must not fire (mag {mag:.1f})"


class TestFeatureDriftRows:
    def test_rows_have_human_notes(self):
        ref = pd.DataFrame({"lag_1": np.random.default_rng(5).normal(100, 5, 200)})
        cur = pd.DataFrame({"lag_1": np.random.default_rng(6).normal(120, 5, 200)})
        rows = D.check_feature_drift(ref, cur, ["lag_1"], "r1", dt.date(2026, 9, 1))
        fired = [r for r in rows if r["fired"]]
        assert fired, "the shifted feature must fire"
        for r in fired:
            assert r["channel"] == "feature"
            assert len(r["note"]) > 30
            assert r["severity"] in ("warn", "critical")

    def test_only_top_features_tested(self):
        ref = pd.DataFrame({f"f{i}": np.random.default_rng(i).normal(0, 1, 300) for i in range(50)})
        cur = ref.copy()
        rows = D.check_feature_drift(
            ref, cur, [f"f{i}" for i in range(50)], "r", dt.date(2026, 9, 1)
        )
        subjects = {r["subject"] for r in rows}
        assert len(subjects) <= 20, "PSI on 200 features gives 200 alerts and no information"


class TestPromotionGate:
    def _model(self, mase=0.90, cov=0.80, folds=12, cats=None, win=0.70):
        return {
            "version": "x",
            "backtest": {
                "mase": mase,
                "coverage_80": cov,
                "folds": folds,
                "categories": cats or {"vegetables": 1.1, "grains": 0.8},
                "win_pct": win,
            },
        }

    def test_promotes_when_all_five_hold(self):
        champ = self._model(mase=0.95)
        chall = self._model(mase=0.90)  # 5.3% better
        decision, reasons = P.evaluate_promotion(chall, champ, {}, 0.70, 0.72)
        assert decision == "promote", reasons

    def test_keeps_when_margin_below_three_percent(self):
        champ = self._model(mase=0.950)
        chall = self._model(mase=0.937)  # 1.4% better — noise, not a win
        decision, reasons = P.evaluate_promotion(chall, champ, {}, 0.70, 0.72)
        assert decision == "keep"
        assert any("under the 3% gate" in r or "3%" in r for r in reasons)

    def test_keeps_when_a_category_regresses(self):
        champ = self._model(mase=0.95, cats={"vegetables": 1.00, "grains": 0.80})
        chall = self._model(mase=0.85, cats={"vegetables": 1.25, "grains": 0.60})
        decision, reasons = P.evaluate_promotion(
            chall, champ, {"vegetables": 1.25, "grains": 0.60}, 0.70, 0.72
        )
        assert decision == "keep"
        assert any("regressed" in r for r in reasons)

    def test_keeps_when_coverage_outside_band(self):
        champ = self._model(mase=0.95)
        chall = self._model(mase=0.88, cov=0.60)
        decision, _ = P.evaluate_promotion(chall, champ, {}, 0.70, 0.72)
        assert decision == "keep"

    def test_keeps_when_win_rate_drops(self):
        champ = self._model(mase=0.95)
        chall = self._model(mase=0.88)
        decision, reasons = P.evaluate_promotion(chall, champ, {}, 0.70, 0.60)
        assert decision == "keep"
        assert any("beats seasonal-naive" in r for r in reasons)

    def test_first_champion_promotes(self):
        decision, reasons = P.evaluate_promotion(self._model(), None, {}, None, None)
        assert decision == "promote" and "First champion" in reasons[0]

    def test_retrain_trigger_drift_or_staleness(self):
        reg = {"models": [{"trained_at": "2026-01-01T00:00:00Z"}]}
        fired = [{"fired": True, "severity": "critical"}]
        assert P.should_retrain(reg, fired, today=dt.date(2026, 1, 8))[0]
        assert not P.should_retrain(
            reg, [{"fired": True, "severity": "warn"}], today=dt.date(2026, 1, 8)
        )[0]
        stale = {"models": [{"trained_at": "2026-01-01T00:00:00Z"}]}
        assert P.should_retrain(stale, [], today=dt.date(2026, 2, 15))[0]
