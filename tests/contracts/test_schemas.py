"""Contract tests: as_of / latest_revision discipline, and schema validation of a
tiny hand-built frame. Fixture-level validation lives in test_fixtures.py."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pandera.errors
import pytest

from contracts.schemas import (
    SCHEMAS,
    as_of,
    latest_revision,
    validate_frame,
)


def _row(week, city="05", item="019", revision=0, avg=100.0, ingested=None, **over):
    d = {
        "week_ending": [week],
        "city_code": [city],
        "city_en": ["Lahore"],
        "city_ur": ["لاہور"],
        "item_code": [item],
        "item_en": ["Onions"],
        "item_ur": ["پیاز"],
        "unit_raw": ["1 Kg"],
        "unit_norm": ["kg"],
        "qty_norm": [1.0],
        "price_min": [avg - 2],
        "price_avg": [avg],
        "price_max": [avg + 2],
        "price_per_unit": [avg],
        "source": ["pbs_spi_annex"],
        "source_url": ["https://fixture.bhao.example/a.xlsx"],
        "ingested_at": [ingested or pd.Timestamp(week + dt.timedelta(days=2), tz="UTC")],
        "revision": [np.int32(revision)],
    }
    d.update({k: [v] for k, v in over.items()})
    return (pd.DataFrame(d)
            .astype({"revision": "int32", "qty_norm": "float64",
                     "ingested_at": "datetime64[us, UTC]"}))


def _week(n: int) -> dt.date:
    return dt.date(2026, 1, 1) + dt.timedelta(weeks=n)


class TestLatestRevision:
    def test_returns_max_revision_per_key(self):
        df = pd.concat([
            _row(_week(1), revision=0, avg=100.0),
            _row(_week(1), revision=1, avg=103.0),
            _row(_week(2), revision=0, avg=101.0),
        ], ignore_index=True)
        out = latest_revision(df)
        assert len(out) == 2
        w1 = out[out["week_ending"] == _week(1)]
        assert float(w1["price_avg"].iloc[0]) == 103.0
        assert int(w1["revision"].iloc[0]) == 1

    def test_never_edits_revision_zero(self):
        df = pd.concat([
            _row(_week(1), revision=0, avg=100.0),
            _row(_week(1), revision=1, avg=103.0),
        ], ignore_index=True)
        out = latest_revision(df)
        assert float(df[df["revision"] == 0]["price_avg"].iloc[0]) == 100.0
        assert len(out) == 1  # the view keeps one row, the source keeps both


class TestAsOf:
    def test_excludes_weeks_after_made_on(self):
        df = pd.concat([_row(_week(1), avg=100.0), _row(_week(2), avg=101.0)], ignore_index=True)
        out = as_of(df, _week(1))
        assert set(out["week_ending"]) == {_week(1)}

    def test_excludes_revision_not_yet_ingested(self):
        # restatement ingested 2026-01-20 must not be visible on 2026-01-15
        df = pd.concat([
            _row(_week(1), revision=0, avg=100.0,
                 ingested=pd.Timestamp("2026-01-10T06:00:00Z")),
            _row(_week(1), revision=1, avg=103.0,
                 ingested=pd.Timestamp("2026-01-20T06:00:00Z")),
        ], ignore_index=True)
        before = as_of(df, dt.date(2026, 1, 15))
        after = as_of(df, dt.date(2026, 1, 21))
        assert len(before) == 1 and float(before["price_avg"].iloc[0]) == 100.0
        assert len(after) == 1 and float(after["price_avg"].iloc[0]) == 103.0

    def test_one_row_per_key(self):
        df = pd.concat([
            _row(_week(1), revision=0, avg=100.0,
                 ingested=pd.Timestamp("2026-01-10T06:00:00Z")),
            _row(_week(1), revision=1, avg=103.0,
                 ingested=pd.Timestamp("2026-01-20T06:00:00Z")),
            _row(_week(2), revision=0, avg=101.0,
                 ingested=pd.Timestamp("2026-01-17T06:00:00Z")),
        ], ignore_index=True)
        out = as_of(df, dt.date(2026, 1, 25))
        assert out.groupby(["week_ending", "city_code", "item_code"]).size().eq(1).all()

    def test_row_ingested_late_is_invisible_until_it_arrives(self):
        # week 2's first publication lands only on 2026-01-25
        df = pd.concat([
            _row(_week(1), avg=100.0, ingested=pd.Timestamp("2026-01-10T06:00:00Z")),
            _row(_week(2), avg=101.0, ingested=pd.Timestamp("2026-01-25T06:00:00Z")),
        ], ignore_index=True)
        out = as_of(df, dt.date(2026, 1, 20))
        assert set(out["week_ending"]) == {_week(1)}

    def test_accepts_iso_string(self):
        df = _row(_week(1))
        out = as_of(df, "2026-01-10")
        assert len(out) == 1


class TestSchemas:
    def test_valid_row_passes(self):
        validate_frame(_row(_week(1)), "prices_weekly")

    def test_price_order_violation_fails(self):
        bad = _row(_week(1), avg=100.0, **{"price_min": [105.0]})
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(bad, "prices_weekly")

    def test_duplicate_key_fails(self):
        df = pd.concat([_row(_week(1)), _row(_week(1))], ignore_index=True)
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(df, "prices_weekly")

    def test_bad_unit_norm_fails(self):
        bad = _row(_week(1), unit_norm="kilograms")
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(bad, "prices_weekly")

    def test_bad_city_code_fails(self):
        bad = _row(_week(1), city="5")
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(bad, "prices_weekly")

    def test_forecast_quantile_crossing_fails(self):
        fc = pd.DataFrame([{
            "run_id": "r1", "model_version": "v1", "model_name": "global_gbm",
            "made_on": _week(1), "target_week": _week(2), "horizon": np.int32(1),
            "city_code": "05", "item_code": "019",
            "p10": 105.0, "p50": 100.0, "p90": 110.0,  # p10 > p50
            "is_champion": True, "features_hash": "abc123",
            "created_at": pd.Timestamp("2026-01-10T06:00:00Z"),
        }]).astype({"horizon": "int32", "is_champion": "bool"})
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(fc, "forecasts")

    def test_drift_severity_enum(self):
        d = pd.DataFrame([{
            "run_id": "r1", "checked_on": _week(1), "channel": "residual",
            "subject": "overall", "test": "rolling_mase", "statistic": 1.3,
            "threshold": 1.14, "p_value": None, "fired": True,
            "severity": "apocalyptic",  # not in enum
            "window_start": _week(1), "window_end": _week(2), "note": "x",
        }]).astype({"fired": "bool"})
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(d, "drift")

    def test_metrics_scope_key_consistency(self):
        def m(scope, city, item):
            return {
                "run_id": "r1", "evaluated_on": _week(3), "target_week": _week(2),
                "model_name": "global_gbm", "model_version": "v1", "scope": scope,
                "city_code": city, "item_code": item, "n_obs": np.int32(10),
                "mase": 0.9, "smape": 4.0, "mae": 10.0, "rmse": 20.0,
                "pinball_10": 1.0, "pinball_50": 5.0, "pinball_90": 1.5,
                "coverage_80": 0.8, "bias": 0.1, "is_backtest": False,
            }

        good = pd.DataFrame([
            m("overall", None, None),
            m("city", "05", None),
            m("item", None, "019"),
            m("administered", None, None),
        ]).astype({"n_obs": "int32", "is_backtest": "bool"})
        validate_frame(good, "metrics")

        bad = pd.DataFrame([m("overall", "05", None)]).astype(
            {"n_obs": "int32", "is_backtest": "bool"})
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(bad, "metrics")

    def test_items_alias_list_type(self):
        it = pd.DataFrame([{
            "item_code": "019", "item_en": "Onions", "item_ur": "پیاز",
            "unit_raw": "1 Kg", "unit_norm": "kg", "qty_norm": 1.0,
            "category": "vegetables", "spi_weight": 1.15, "is_food": True,
            "is_administered": False, "pbs_aliases": ["Onions"],
            "first_seen": _week(0), "last_seen": _week(1), "notes": None,
        }]).astype({"qty_norm": "float64", "is_food": "bool", "is_administered": "bool"})
        validate_frame(it, "items")
        it_bad = it.copy()
        it_bad["pbs_aliases"] = ["not-a-list"]
        with pytest.raises(pandera.errors.SchemaErrors):
            validate_frame(it_bad, "items")

    def test_extra_columns_are_allowed(self):
        df = _row(_week(1))
        df["some_future_column"] = 42
        validate_frame(df, "prices_weekly")
