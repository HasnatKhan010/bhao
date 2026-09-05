"""API tests — one per Contract 3 route, against fixtures.

Asserts the envelope shape, `meta` presence (including `is_fixture`), the error
cases, and the two places the API makes a judgment: `direction` and `recent_error`.
"""

from __future__ import annotations

import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("BHAO_DATA_DIR", "contracts/fixtures")


@pytest.fixture(scope="module")
def client():
    from api.main import app

    return TestClient(app)


def _meta_ok(body: dict) -> None:
    assert "meta" in body, "every list response carries meta"
    meta = body["meta"]
    for key in ("generated_at", "panel_week", "model_version", "is_fixture"):
        assert key in meta, f"meta must carry {key}"
    assert meta["panel_week"], "a client must always be able to tell how fresh the answer is"


class TestHealth:
    def test_shape(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        b = r.json()
        for key in ("status", "panel_week", "forecast_run_id", "model_version",
                    "rows", "uptime_s", "is_fixture"):
            assert key in b
        assert b["rows"] > 0

    def test_not_cached(self, client):
        r = client.get("/api/health")
        assert "no-store" in r.headers.get("cache-control", "")

    def test_reports_stale_panel_as_degraded(self, client):
        # the fixture panel ends 2026-08-20; a panel older than 10 days is degraded,
        # which is the only thing that catches "the weekly run silently didn't happen"
        b = client.get("/api/health").json()
        age = b["panel_age_days"]
        assert (b["status"] == "ok") == (age is not None and age <= 10)


class TestFixtureBanner:
    def test_is_fixture_true_when_serving_fixtures(self, client):
        assert client.get("/api/health").json()["is_fixture"] is True
        assert client.get("/api/cities").json()["meta"]["is_fixture"] is True

    def test_registry_marks_fixture(self, client):
        b = client.get("/api/model").json()
        assert b["data"]["meta"]["is_fixture"] is True


class TestCities:
    def test_returns_all_cities_with_both_languages(self, client):
        b = client.get("/api/cities").json()
        _meta_ok(b)
        assert len(b["data"]) == 18  # 17 cities + national
        first = b["data"][0]
        assert first["city_en"] and first["city_ur"]
        assert first["province_en"] and first["province_ur"]

    def test_both_labels_present_regardless_of_lang(self, client):
        for lang in ("en", "ur"):
            row = client.get(f"/api/cities?lang={lang}").json()["data"][1]
            assert row["city_en"] and row["city_ur"], "no round trip to switch language"


class TestItems:
    def test_list_and_filter_by_category(self, client):
        b = client.get("/api/items").json()
        _meta_ok(b)
        assert len(b["data"]) == 51
        veg = client.get("/api/items?category=vegetables").json()["data"]
        assert veg and all(i["category"] == "vegetables" for i in veg)

    def test_filter_by_city(self, client):
        b = client.get("/api/items?city_code=05").json()
        assert len(b["data"]) > 0

    def test_unknown_city_is_404_naming_the_city(self, client):
        r = client.get("/api/items?city_code=99")
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["code"] == "CITY_NOT_FOUND"
        assert "99" in err["message"]


class TestPrices:
    def test_series_shape(self, client):
        b = client.get("/api/prices?city_code=05&item_code=019&limit=5").json()
        _meta_ok(b)
        assert len(b["data"]) == 5
        row = b["data"][0]
        for key in ("week_ending", "price_min", "price_avg", "price_max",
                    "price_per_unit", "revision", "source_url"):
            assert key in row
        assert row["source_url"], "provenance per row"

    def test_date_range_filter(self, client):
        b = client.get("/api/prices?city_code=05&item_code=019"
                       "&from=2026-01-01&to=2026-03-01").json()
        weeks = [dt.date.fromisoformat(r["week_ending"]) for r in b["data"]]
        assert weeks and all(dt.date(2026, 1, 1) <= w <= dt.date(2026, 3, 1) for w in weeks)

    def test_latest_revision_only(self, client):
        # the fixture plants one restatement; /api/prices must serve the current view
        b = client.get("/api/prices?city_code=05&item_code=019&limit=500").json()
        weeks = [r["week_ending"] for r in b["data"]]
        assert len(weeks) == len(set(weeks)), "one row per week — latest revision only"

    def test_empty_range_is_404(self, client):
        r = client.get("/api/prices?city_code=05&item_code=019&from=2030-01-01")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NO_DATA_FOR_RANGE"


class TestForecast:
    def test_carries_forecast_and_its_trustworthiness_together(self, client):
        b = client.get("/api/forecast?city_code=05&item_code=019").json()
        for key in ("p10", "p50", "p90", "last_actual", "last_actual_week", "direction",
                    "pct_change_expected", "model_version", "made_on", "history",
                    "recent_error"):
            assert key in b
        assert b["recent_error"]["n_weeks"] >= 0, "the forecast and its error arrive together"

    def test_quantiles_are_ordered(self, client):
        b = client.get("/api/forecast?city_code=05&item_code=019").json()
        assert b["p10"] <= b["p50"] <= b["p90"]

    def test_both_language_labels_present(self, client):
        b = client.get("/api/forecast?city_code=10&item_code=001").json()
        assert b["city_en"] == "Karachi" and b["city_ur"]
        assert b["item_en"] and b["item_ur"]

    def test_history_is_ascending_and_bounded(self, client):
        b = client.get("/api/forecast?city_code=05&item_code=019&history_weeks=10").json()
        weeks = [dt.date.fromisoformat(h["week_ending"]) for h in b["history"]]
        assert len(weeks) <= 10
        assert weeks == sorted(weeks)

    def test_direction_is_measured_against_the_series_own_error(self, client):
        from api.main import _direction

        # a 0.4-rupee move on a series whose weekly MAE is 3.0 is NOT a rise
        assert _direction(0.4, None, 3.0) == "flat"
        assert _direction(5.0, None, 3.0) == "up"
        assert _direction(-5.0, None, 3.0) == "down"
        # a fixed-percentage rule would have called the first one "up"
        assert _direction(None, None, 3.0) == "flat"
        assert _direction(1.0, None, None) == "flat", "no bar means no claim"

    def test_unknown_item_names_the_item(self, client):
        r = client.get("/api/forecast?city_code=05&item_code=888")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "ITEM_NOT_FOUND"
        assert "888" in r.json()["error"]["message"]


class TestMovers:
    def test_ranked_movers(self, client):
        b = client.get("/api/movers?limit=5").json()
        _meta_ok(b)
        assert len(b["data"]) > 0
        assert b["data"][0]["rank"] == 1
        assert "item_ur" in b["data"][0]

    def test_direction_filter(self, client):
        up = client.get("/api/movers?limit=3&direction=up").json()["data"]
        down = client.get("/api/movers?limit=3&direction=down").json()["data"]
        assert len(up) <= 3 and len(down) <= 3
        assert up[0]["pct_change"] >= up[-1]["pct_change"]


class TestScorecard:
    def test_overall_scope(self, client):
        b = client.get("/api/scorecard?scope=overall").json()
        _meta_ok(b)
        assert len(b["data"]) > 0
        row = b["data"][0]
        for key in ("target_week", "model_name", "mase", "smape", "mae",
                    "coverage_80", "bias", "n_obs"):
            assert key in row

    def test_baselines_are_present_so_the_reader_sees_what_was_beaten(self, client):
        rows = client.get("/api/scorecard?scope=overall&limit=200").json()["data"]
        names = {r["model_name"] for r in rows}
        assert "global_gbm" in names
        assert names & {"seasonal_naive", "random_walk"}, (
            "the scorecard must show what the model beat"
        )

    def test_per_item_scope(self, client):
        rows = client.get("/api/scorecard?scope=item&item_code=019").json()["data"]
        assert all(r["item_code"] == "019" for r in rows)


class TestDrift:
    def test_rows_and_human_notes(self, client):
        b = client.get("/api/drift").json()
        _meta_ok(b)
        assert len(b["data"]) > 0
        for row in b["data"]:
            assert len(row["note"]) > 20, "notes are sentences a journalist could quote"

    def test_severity_filter(self, client):
        rows = client.get("/api/drift?severity=critical").json()["data"]
        assert rows and all(r["severity"] == "critical" for r in rows)
        assert any(r["fired"] for r in rows)


class TestModel:
    def test_registry_and_promotion_log(self, client):
        b = client.get("/api/model").json()
        reg = b["data"]
        assert reg["champion"]
        assert reg["models"] and reg["promotion_log"]
        entry = reg["promotion_log"][0]
        assert entry["decision"] in ("promote", "keep")
        assert len(entry["reason"]) > 20, "promotion reasons are English, not dict dumps"


class TestDataset:
    def test_parquet_redirects(self, client):
        r = client.get("/api/download/panel.parquet", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"].endswith(".parquet")

    def test_csv_streams_with_headers(self, client):
        r = client.get("/api/download/panel.csv?city_code=05&item_code=019")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        first_line = r.text.splitlines()[0]
        assert "week_ending" in first_line and "source_url" in first_line


class TestConventions:
    def test_json_routes_are_cached(self, client):
        r = client.get("/api/cities")
        assert "max-age" in r.headers.get("cache-control", "")

    def test_cors_is_open_for_get(self, client):
        r = client.get("/api/cities", headers={"Origin": "https://example.com"})
        assert r.headers.get("access-control-allow-origin") == "*"

    def test_openapi_is_served(self, client):
        r = client.get("/api/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        for route in ("/api/health", "/api/cities", "/api/items", "/api/prices",
                      "/api/forecast", "/api/movers", "/api/scorecard", "/api/drift",
                      "/api/model", "/api/download/panel.parquet", "/api/download/panel.csv"):
            assert route in paths, f"Contract 3 route {route} missing from OpenAPI"

    def test_api_does_not_import_training_code(self):
        # trap #1: the moment api/ imports LightGBM the container triples in size
        # and a training bug can break the site. Checked in a CLEAN subprocess —
        # sys.modules in this process is already polluted by the model tests.
        import subprocess
        import sys
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2]
        code = (
            "import sys; import api.main; "
            "banned=[m for m in ('lightgbm','statsmodels','models.global_gbm',"
            "'features.build','ingest.fetch') if m in sys.modules]; "
            "print(','.join(banned))"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], cwd=repo, capture_output=True, text=True,
            env={**os.environ, "BHAO_DATA_DIR": "contracts/fixtures"},
        )
        assert out.returncode == 0, out.stderr
        leaked = out.stdout.strip()
        assert not leaked, f"api must not import: {leaked}"

    def test_no_write_methods(self, client):
        for method in ("post", "put", "delete", "patch"):
            r = getattr(client, method)("/api/cities")
            assert r.status_code in (404, 405), "v1 is read-only"
