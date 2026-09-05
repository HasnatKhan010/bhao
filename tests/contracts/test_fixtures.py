"""Fixture pathology tests — every planted pathology must provably exist.

These are the tests Gate 0 requires: "All nine planted pathologies present, each with
a test asserting it exists." Fixtures are regenerated in-memory (deterministic seed),
so these tests hold for regeneration too.
"""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from contracts.fixtures.make_fixtures import (
    ADMIN_STEP_CODE,
    ADMIN_STEP_PCT,
    ADMIN_STEP_WEEK,
    FIRST_WEEK,
    MISSING_CITY,
    MISSING_CITY_WEEKS,
    RAGGED_CODES,
    RAGGED_START,
    REVISION_KEY,
    SCALE_HIGH_CODE,
    SCALE_LOW_CODE,
    VARIANCE_CODE,
    VARIANCE_MULT,
    WEEKS,
    generate_all,
)
from contracts.schemas import ALL_MODELS, as_of


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    out = tmp_path_factory.mktemp("fx")
    named = generate_all(out)
    # round-trip through parquet, exactly as consumers read them
    loaded = {name: pd.read_parquet(out / f"{name}.parquet") for name in named}
    return out, named, loaded


@pytest.fixture(scope="module")
def panel(fixtures):
    return fixtures[2]["prices_weekly"]


# --- every fixture file validates against the executable contract -------------


class TestSchemasHold:
    @pytest.mark.parametrize("name", list(ALL_MODELS))
    def test_validates_against_contract(self, fixtures, name):
        _, named, loaded = fixtures
        ALL_MODELS[name].validate(loaded[name], lazy=True)


# --- the nine pathologies -----------------------------------------------------


class TestPathologies:
    def test_1_ragged_series_start(self, panel):
        for code in RAGGED_CODES:
            sub = panel[panel["item_code"] == code]
            first = sub["week_ending"].min()
            assert first == WEEKS[RAGGED_START], f"item {code} starts {first}"
            other = panel[panel["item_code"] == "001"]["week_ending"].min()
            assert other == FIRST_WEEK

    def test_2_missing_cells(self, panel):
        frac = panel["price_avg"].isna().mean()
        assert 0.02 < frac < 0.07, f"missing fraction {frac:.3f} not ~4%"

    def test_3_whole_city_missing_for_six_weeks(self, panel):
        sub = panel[panel["city_code"] == MISSING_CITY]
        assert not sub["week_ending"].isin(MISSING_CITY_WEEKS).any()
        # present again afterwards
        after = sub[sub["week_ending"] > MISSING_CITY_WEEKS[-1]]
        assert len(after) > 0

    def test_4_item_renamed_mid_series(self, fixtures):
        _, _, loaded = fixtures
        items = loaded["items"]
        aliases = items.loc[items["item_code"] == "004", "pbs_aliases"].iloc[0]
        assert len(aliases) >= 2  # parquet list<string> may read back as ndarray
        assert set(aliases) == {"Rice Irri-6 (Export Quality)", "Rice IRRI-6"}

    def test_5a_revision_rows_exist_and_differ(self, panel):
        wk, city, item = REVISION_KEY
        sub = panel[
            (panel["week_ending"] == wk)
            & (panel["city_code"] == city)
            & (panel["item_code"] == item)
        ]
        assert sorted(sub["revision"].tolist()) == [0, 1]
        r0 = sub[sub["revision"] == 0]["price_avg"].iloc[0]
        r1 = sub[sub["revision"] == 1]["price_avg"].iloc[0]
        assert abs(r1 / r0 - 1.03) < 1e-3  # 2dp rounding of a 2dp base price

    def test_5b_as_of_sees_revision_only_when_knowable(self, panel):
        wk, city, item = REVISION_KEY
        key = ["week_ending", "city_code", "item_code"]
        rev1_date = dt.date(2026, 8, 23)  # revision ingested 2026-08-24 UTC
        before = as_of(panel, dt.date(2026, 8, 22))
        after = as_of(panel, dt.date(2026, 8, 25))
        b = before[
            (before[key[0]] == wk) & (before["city_code"] == city) & (before["item_code"] == item)
        ]
        a = after[
            (after[key[0]] == wk) & (after["city_code"] == city) & (after["item_code"] == item)
        ]
        assert int(b["revision"].iloc[0]) == 0
        assert int(a["revision"].iloc[0]) == 1
        assert rev1_date > dt.date(2026, 8, 22)

    def test_6_administered_step_change(self, panel):
        sub = panel[(panel["item_code"] == ADMIN_STEP_CODE) & (panel["city_code"] == "05")]
        sub = sub[sub["revision"] == 0].sort_values("week_ending")
        avgs = sub["price_avg"].to_numpy(dtype=float)
        weeks = sub["week_ending"].to_numpy()
        step_i = np.where(weeks == WEEKS[ADMIN_STEP_WEEK])[0][0]
        # flat 20 weeks either side (NaN-tolerant: the missing-cells pathology also
        # nulls a few of these rows — that is pathology 2 doing its job)
        pre = avgs[step_i - 20 : step_i]
        post = avgs[step_i : step_i + 20]
        assert np.allclose(pre[~np.isnan(pre)], pre[~np.isnan(pre)][0])
        assert np.allclose(post[~np.isnan(post)], post[~np.isnan(post)][0])
        ratio = post[~np.isnan(post)][0] / pre[~np.isnan(pre)][0]
        assert abs(ratio - (1 + ADMIN_STEP_PCT)) < 5e-3
        # single-price series: min == avg == max wherever present
        ok = sub[["price_min", "price_avg", "price_max"]].dropna()
        assert (ok["price_min"] == ok["price_avg"]).all()
        assert (ok["price_max"] == ok["price_avg"]).all()

    def test_7_variance_regime_shift(self, panel):
        sub = panel[(panel["item_code"] == VARIANCE_CODE) & (panel["city_code"] == "05")]
        sub = sub[sub["revision"] == 0].sort_values("week_ending")
        s = pd.Series(sub["price_avg"].to_numpy(), index=pd.to_datetime(sub["week_ending"]))
        rets = np.log(s).diff().dropna()
        early = rets[rets.index < pd.Timestamp(WEEKS[100])]
        late = rets[rets.index >= pd.Timestamp(WEEKS[105])]
        ratio = late.std() / early.std()
        assert ratio > VARIANCE_MULT * 0.6, f"variance ratio {ratio:.2f} should be ~{VARIANCE_MULT}"

    def test_8_extreme_scale_spread(self, panel):
        lo = panel[panel["item_code"] == SCALE_LOW_CODE]["price_avg"].dropna()
        hi = panel[panel["item_code"] == SCALE_HIGH_CODE]["price_avg"].dropna()
        assert lo.max() < 5.0
        assert hi.min() > 12000.0

    def test_9_unicode_and_zwnj_survive_roundtrip(self, fixtures):
        _, _, loaded = fixtures
        items = loaded["items"]
        ur_033 = items.loc[items["item_code"] == "033", "item_ur"].iloc[0]
        assert "\u200c" in ur_033, "ZWNJ must survive the parquet round-trip"
        assert any(0x0600 <= ord(ch) <= 0x06FF for ch in ur_033)
        cities = loaded["cities"]
        assert cities.loc[cities["city_code"] == "10", "city_ur"].iloc[0] == "کراچی"


class TestPanelInvariants:
    def test_key_uniqueness(self, panel):
        keys = ["week_ending", "city_code", "item_code", "revision"]
        assert not panel.duplicated(keys).any()

    def test_min_le_avg_le_max_where_present(self, panel):
        p = panel
        ok = ~(
            (p["price_min"].notna()) & (p["price_avg"].notna()) & (p["price_min"] > p["price_avg"])
        )
        ok &= ~(
            (p["price_max"].notna()) & (p["price_avg"].notna()) & (p["price_max"] < p["price_avg"])
        )
        assert ok.all()

    def test_weeks_are_thursdays(self, panel):
        assert (pd.to_datetime(panel["week_ending"]).dt.weekday == 3).all()

    def test_codes_are_zero_padded_strings(self, panel):
        assert panel["city_code"].str.fullmatch(r"\d{2}").all()
        assert panel["item_code"].str.fullmatch(r"\d{3}").all()

    def test_panel_shape_is_867_series(self, panel):
        n_series = panel[panel["revision"] == 0].groupby(["city_code", "item_code"]).ngroups
        assert n_series == 867

    def test_deterministic_regeneration(self, fixtures):
        out, named, _ = fixtures
        again = generate_all(out)
        for name in ("prices_weekly", "forecasts", "metrics", "drift"):
            a = named[name].sort_values(list(named[name].columns)[:4]).reset_index(drop=True)
            b = again[name].sort_values(list(again[name].columns)[:4]).reset_index(drop=True)
            pd.testing.assert_frame_equal(a, b)


class TestForecastsFixture:
    def test_champion_uniqueness(self, fixtures):
        _, _, loaded = fixtures
        fc = loaded["forecasts"]
        champ = fc[fc["is_champion"]]
        assert (champ.groupby(["city_code", "item_code", "target_week"]).size() == 1).all()
        assert champ["model_name"].eq("global_gbm").all()

    def test_baselines_written_too(self, fixtures):
        _, _, loaded = fixtures
        fc = loaded["forecasts"]
        assert {"global_gbm", "seasonal_naive", "random_walk"} <= set(fc["model_name"])

    def test_some_p50_null(self, fixtures):
        # a series without a 52-week-lagged value has a null seasonal-naive p50
        _, _, loaded = fixtures
        fc = loaded["forecasts"]
        assert fc["p50"].isna().any()

    def test_metrics_have_scopes_and_both_kinds(self, fixtures):
        _, _, loaded = fixtures
        m = loaded["metrics"]
        assert {"overall", "category", "item", "administered", "city"} <= set(m["scope"])
        assert {True, False} <= set(m["is_backtest"])

    def test_drift_has_fired_rows_with_human_notes(self, fixtures):
        _, _, loaded = fixtures
        d = loaded["drift"]
        fired = d[d["fired"]]
        assert len(fired) > 0
        assert (fired["note"].str.len() > 20).all()
        assert "critical" in set(fired["severity"])

    def test_registry_is_fixture(self, fixtures):
        reg = json.loads((fixtures[0] / "model_registry.json").read_text(encoding="utf-8"))
        assert reg["meta"]["is_fixture"] is True
        assert reg["champion"].startswith("gbm-")
