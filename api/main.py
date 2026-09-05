"""Bhao API — Contract 3. Read-only, no auth, public data.

Security note: this is deliberately an unauthenticated read-only surface. There are
no writes, no user data and nothing to protect (07-TRACK-C-SERVE.md trap #6), so the
only abuse vector is volume — handled by the per-IP rate limit below. Do not add a
POST route without revisiting that reasoning.
"""

from __future__ import annotations

import datetime as dt
import io
import time
from collections import defaultdict, deque

import pandas as pd
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from api import store as S
from api.schemas import (
    City,
    DriftRow,
    ErrorBody,
    ErrorResponse,
    Forecast,
    Health,
    HistoryPoint,
    Item,
    ListResponse,
    Meta,
    Mover,
    PricePoint,
    RecentError,
    ScorecardRow,
)

app = FastAPI(
    title="Bhao API",
    version="0.1.0",
    description=(
        "What things cost in Pakistan, weekly — and what they'll cost next week. "
        "Read-only public data from the Pakistan Bureau of Statistics weekly SPI, "
        "normalised into a tidy panel, with h=1-week forecasts and their published error."
    ),
    docs_url="/api-docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # public data; GET only
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# --- errors -------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, **detail):
        self.code, self.message, self.status, self.detail = code, message, status, detail


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status,
        content=ErrorResponse(
            error=ErrorBody(code=exc.code, message=exc.message, detail=exc.detail)
        ).model_dump(),
    )


@app.exception_handler(FileNotFoundError)
async def _missing_data(_: Request, exc: FileNotFoundError):
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error=ErrorBody(code="INTERNAL", message=str(exc))
        ).model_dump(),
    )


# --- rate limiting + caching --------------------------------------------------

_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def _rate_limit(request: Request, bucket: str, per_minute: int) -> None:
    ip = request.client.host if request.client else "unknown"
    key = (ip, bucket)
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_minute:
        raise ApiError(
            "RATE_LIMITED",
            f"more than {per_minute} requests per minute from this IP",
            status=429,
            retry_after_s=int(60 - (now - q[0])),
        )
    q.append(now)


@app.middleware("http")
async def _cache_and_limit(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/download/panel.csv"):
        _rate_limit(request, "csv", S.RATE_LIMIT_CSV)
    elif path.startswith("/api/"):
        _rate_limit(request, "json", S.RATE_LIMIT_JSON)
    try:
        response = await call_next(request)
    except ApiError as exc:                       # raised inside the middleware chain
        return await _api_error(request, exc)
    if path.startswith("/api/") and path != "/api/health":
        response.headers.setdefault("Cache-Control", f"public, max-age={S.CACHE_TTL_SECONDS}")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _meta() -> Meta:
    m = S.store().meta()
    return Meta(
        generated_at=dt.datetime.now(dt.UTC),
        panel_week=pd.to_datetime(m["panel_week"]).date() if m.get("panel_week") else None,
        model_version=m.get("model_version"),
        is_fixture=m.get("is_fixture", False),
        rows=m.get("rows"),
        forecast_run_id=m.get("forecast_run_id"),
    )


def _as_date(v) -> dt.date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return pd.to_datetime(v).date()


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else round(f, 4)


# --- routes -------------------------------------------------------------------


@app.get("/api/health", response_model=Health, tags=["ops"])
def health():
    st = S.store()
    m = st.meta()
    panel_week = _as_date(m.get("panel_week"))
    age = (dt.date.today() - panel_week).days if panel_week else None
    # a stale panel serves confidently — say so rather than looking healthy
    ok = panel_week is not None and (age is not None and age <= 10)
    return Health(
        status="ok" if ok else "degraded",
        panel_week=panel_week,
        forecast_run_id=m.get("forecast_run_id"),
        model_version=m.get("model_version"),
        rows=m.get("rows"),
        uptime_s=S.uptime_s(),
        is_fixture=m.get("is_fixture", False),
        panel_age_days=age,
    )


@app.get("/api/cities", response_model=ListResponse[City], tags=["reference"])
def cities(lang: str = Query("en", pattern="^(en|ur)$")):
    st = S.store()
    q = f"""
        SELECT c.city_code, c.city_en, c.city_ur, c.province_en, c.province_ur,
               COALESCE(p.n_items, 0) AS n_items
        FROM {st.scan('cities')} c
        LEFT JOIN (
            SELECT city_code, count(DISTINCT item_code) AS n_items
            FROM {st.scan('prices_weekly')} GROUP BY city_code
        ) p USING (city_code)
        ORDER BY c.pbs_order
    """
    df = st.df(q)
    return ListResponse[City](
        data=[City(**{**r, "n_items": int(r["n_items"])}) for r in df.to_dict("records")],
        meta=_meta(),
    )


@app.get("/api/items", response_model=ListResponse[Item], tags=["reference"])
def items(
    lang: str = Query("en", pattern="^(en|ur)$"),
    category: str | None = None,
    city_code: str | None = None,
):
    st = S.store()
    where, params = [], []
    if category:
        where.append("i.category = ?")
        params.append(category)
    if city_code:
        where.append(
            f"i.item_code IN (SELECT DISTINCT item_code FROM {st.scan('prices_weekly')} WHERE city_code = ?)"
        )
        params.append(city_code)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    df = st.df(
        f"""SELECT i.item_code, i.item_en, i.item_ur, i.unit_raw, i.unit_norm,
                   i.qty_norm, i.category, i.is_food, i.is_administered
            FROM {st.scan('items')} i {clause} ORDER BY i.item_code""",
        params,
    )
    if city_code and df.empty:
        raise ApiError("CITY_NOT_FOUND", f"no items surveyed for city {city_code}",
                       status=404, city_code=city_code)
    return ListResponse[Item](data=[Item(**r) for r in df.to_dict("records")], meta=_meta())


@app.get("/api/prices", response_model=ListResponse[PricePoint], tags=["panel"])
def prices(
    city_code: str | None = None,
    item_code: str | None = None,
    from_: dt.date | None = Query(None, alias="from"),
    to: dt.date | None = None,
    limit: int = Query(1000, ge=1, le=20000),
):
    st = S.store()
    where, params = ["revision = (SELECT max(revision) FROM " + st.scan("prices_weekly") +
                     " x WHERE x.week_ending = p.week_ending AND x.city_code = p.city_code"
                     " AND x.item_code = p.item_code)"], []
    if city_code:
        where.append("p.city_code = ?")
        params.append(city_code)
    if item_code:
        where.append("p.item_code = ?")
        params.append(item_code)
    if from_:
        where.append("p.week_ending >= ?")
        params.append(from_)
    if to:
        where.append("p.week_ending <= ?")
        params.append(to)
    df = st.df(
        f"""SELECT p.week_ending, p.city_code, p.item_code, p.price_min, p.price_avg,
                   p.price_max, p.price_per_unit, p.revision, p.source_url
            FROM {st.scan('prices_weekly')} p
            WHERE {' AND '.join(where)}
            ORDER BY p.week_ending DESC LIMIT {int(limit)}""",
        params,
    )
    if df.empty:
        raise ApiError(
            "NO_DATA_FOR_RANGE", "no rows match that city/item/date range", status=404,
            city_code=city_code, item_code=item_code,
            **({"from": str(from_)} if from_ else {}), **({"to": str(to)} if to else {}),
        )
    rows = [
        PricePoint(
            week_ending=_as_date(r["week_ending"]), city_code=r["city_code"],
            item_code=r["item_code"], price_min=_f(r["price_min"]),
            price_avg=_f(r["price_avg"]), price_max=_f(r["price_max"]),
            price_per_unit=_f(r["price_per_unit"]), revision=int(r["revision"]),
            source_url=r["source_url"],
        )
        for r in df.to_dict("records")
    ]
    return ListResponse[PricePoint](data=rows, meta=_meta())


# --- forecast: the one place the API makes a judgment -------------------------


def _recent_error(st: S.Store, city_code: str, item_code: str, n_weeks: int = 8) -> RecentError:
    """Realised error for this series over the last n_weeks of live scoring.

    Falls back to the overall scope when there is no per-series row yet — the app
    must always be able to show the forecast *and* how much to trust it together.
    """
    if not st.has("metrics"):
        return RecentError(mase=None, mase_rw=None, mae=None, n_weeks=0)
    cols = {c.lower() for c in st.df(f"SELECT * FROM {st.scan('metrics')} LIMIT 0").columns}
    mase_rw = "mase_rw" if "mase_rw" in cols else "NULL AS mase_rw"
    df = st.df(
        f"""SELECT avg(mase) AS mase, avg({'mase_rw' if 'mase_rw' in cols else 'NULL'}) AS mase_rw,
                   avg(mae) AS mae, count(*) AS n
            FROM {st.scan('metrics')}
            WHERE scope = 'item' AND item_code = ? AND is_backtest = FALSE""",
        [item_code],
    )
    row = df.iloc[0] if len(df) else None
    if row is None or not row["n"]:
        df = st.df(
            f"""SELECT avg(mase) AS mase, avg({'mase_rw' if 'mase_rw' in cols else 'NULL'}) AS mase_rw,
                       avg(mae) AS mae, count(*) AS n
                FROM {st.scan('metrics')} WHERE scope = 'overall'"""
        )
        row = df.iloc[0] if len(df) else None
    if row is None:
        return RecentError(mase=None, mase_rw=None, mae=None, n_weeks=0)
    return RecentError(
        mase=_f(row["mase"]), mase_rw=_f(row["mase_rw"]),
        mae=_f(row["mae"]), n_weeks=int(row["n"] or 0),
    )


def _direction(expected_change: float | None, recent_mae: float | None,
               series_mae: float | None) -> str:
    """up / down / flat, decided against the series' OWN recent error — not a fixed
    percentage. A 0.4% "rise" on a series that routinely moves 3% is not a rise, and
    calling it one would be the same dishonesty as a faked search result.
    """
    if expected_change is None:
        return "flat"
    bar = next((b for b in (recent_mae, series_mae) if b is not None and b > 0), None)
    if bar is None:
        return "flat"
    if abs(expected_change) < bar:
        return "flat"
    return "up" if expected_change > 0 else "down"


@app.get("/api/forecast", response_model=Forecast, tags=["forecast"])
def forecast(city_code: str, item_code: str, history_weeks: int = Query(52, ge=4, le=520)):
    st = S.store()
    labels = st.df(
        f"""SELECT c.city_en, c.city_ur, i.item_en, i.item_ur, i.unit_raw
            FROM {st.scan('cities')} c, {st.scan('items')} i
            WHERE c.city_code = ? AND i.item_code = ?""",
        [city_code, item_code],
    )
    if labels.empty:
        exists_city = st.sql(f"SELECT 1 FROM {st.scan('cities')} WHERE city_code = ?", [city_code])
        if not exists_city:
            raise ApiError("CITY_NOT_FOUND", f"unknown city {city_code}", status=404,
                           city_code=city_code)
        raise ApiError("ITEM_NOT_FOUND", f"unknown item {item_code}", status=404,
                       item_code=item_code)
    lab = labels.iloc[0]

    hist = st.df(
        f"""SELECT week_ending, price_avg
            FROM {st.scan('prices_weekly')} p
            WHERE city_code = ? AND item_code = ?
              AND revision = (SELECT max(revision) FROM {st.scan('prices_weekly')} x
                              WHERE x.week_ending = p.week_ending AND x.city_code = p.city_code
                                AND x.item_code = p.item_code)
            ORDER BY week_ending DESC LIMIT {int(history_weeks)}""",
        [city_code, item_code],
    ).sort_values("week_ending")

    fc = pd.DataFrame()
    if st.has("forecasts"):
        fc = st.df(
            f"""SELECT * FROM {st.scan('forecasts')}
                WHERE city_code = ? AND item_code = ? AND is_champion = TRUE
                ORDER BY target_week DESC, created_at DESC LIMIT 1""",
            [city_code, item_code],
        )

    last_actual = last_week = None
    if not hist.empty:
        tail = hist.dropna(subset=["price_avg"])
        if not tail.empty:
            last_actual = _f(tail["price_avg"].iloc[-1])
            last_week = _as_date(tail["week_ending"].iloc[-1])

    series_mae = None
    if len(hist.dropna(subset=["price_avg"])) >= 3:
        y = hist["price_avg"].dropna().to_numpy(dtype=float)
        series_mae = float(abs(y[1:] - y[:-1]).mean())

    err = _recent_error(st, city_code, item_code)
    p10 = p50 = p90 = None
    target_week = made_on = None
    model_version = st.meta().get("model_version")
    if not fc.empty:
        r = fc.iloc[0]
        p10, p50, p90 = _f(r["p10"]), _f(r["p50"]), _f(r["p90"])
        target_week, made_on = _as_date(r["target_week"]), _as_date(r["made_on"])
        model_version = r.get("model_version") or model_version

    expected = (p50 - last_actual) if (p50 is not None and last_actual is not None) else None
    pct = (expected / last_actual * 100) if (expected is not None and last_actual) else None

    return Forecast(
        city_code=city_code, item_code=item_code,
        city_en=lab["city_en"], city_ur=lab["city_ur"],
        item_en=lab["item_en"], item_ur=lab["item_ur"], unit_raw=lab["unit_raw"],
        target_week=target_week, p10=p10, p50=p50, p90=p90,
        last_actual=last_actual, last_actual_week=last_week,
        direction=_direction(expected, err.mae, series_mae),
        pct_change_expected=_f(pct), model_version=model_version, made_on=made_on,
        history=[
            HistoryPoint(week_ending=_as_date(r["week_ending"]), price_avg=_f(r["price_avg"]))
            for r in hist.to_dict("records")
        ],
        recent_error=err,
    )


@app.get("/api/movers", response_model=ListResponse[Mover], tags=["panel"])
def movers(
    city_code: str | None = None,
    window: int = Query(1, ge=1, le=52),
    limit: int = Query(10, ge=1, le=100),
    direction: str = Query("both", pattern="^(up|down|both)$"),
):
    st = S.store()
    weeks = st.sql(
        f"SELECT DISTINCT week_ending FROM {st.scan('prices_weekly')} ORDER BY week_ending DESC LIMIT {window + 1}"
    )
    if len(weeks) < 2:
        raise ApiError("NO_DATA_FOR_RANGE", "panel has fewer than two weeks", status=404)
    latest, earlier = weeks[0][0], weeks[-1][0]
    scope = "AND city_code = ?" if city_code else ""
    params = [latest] + ([city_code] if city_code else []) + [earlier] + ([city_code] if city_code else [])
    df = st.df(
        f"""WITH cur AS (
                SELECT item_code, avg(price_avg) AS p FROM {st.scan('prices_weekly')}
                WHERE week_ending = ? {scope} GROUP BY item_code
            ), prev AS (
                SELECT item_code, avg(price_avg) AS p FROM {st.scan('prices_weekly')}
                WHERE week_ending = ? {scope} GROUP BY item_code
            )
            SELECT i.item_code, i.item_en, i.item_ur, cur.p AS price_avg,
                   (cur.p / prev.p - 1) * 100 AS pct_change
            FROM cur JOIN prev USING (item_code) JOIN {st.scan('items')} i USING (item_code)
            WHERE prev.p > 0 AND cur.p IS NOT NULL
            ORDER BY pct_change DESC""",
        params,
    )
    if direction == "up":
        df = df.head(limit)
    elif direction == "down":
        df = df.tail(limit).iloc[::-1]
    else:
        df = pd.concat([df.head(limit), df.tail(limit)]).drop_duplicates("item_code")
    rows = [
        Mover(item_code=r["item_code"], item_en=r["item_en"], item_ur=r["item_ur"],
              price_avg=_f(r["price_avg"]), pct_change=_f(r["pct_change"]), rank=i + 1)
        for i, r in enumerate(df.to_dict("records"))
    ]
    return ListResponse[Mover](data=rows, meta=_meta())


@app.get("/api/scorecard", response_model=ListResponse[ScorecardRow], tags=["accuracy"])
def scorecard(
    scope: str = Query("overall"),
    city_code: str | None = None,
    item_code: str | None = None,
    model_name: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
):
    st = S.store()
    if not st.has("metrics"):
        return ListResponse[ScorecardRow](data=[], meta=_meta())
    cols = {c.lower() for c in st.df(f"SELECT * FROM {st.scan('metrics')} LIMIT 0").columns}
    mase_rw_expr = "mase_rw" if "mase_rw" in cols else "NULL AS mase_rw"
    where, params = ["scope = ?"], [scope]
    if city_code:
        where.append("city_code = ?")
        params.append(city_code)
    if item_code:
        where.append("item_code = ?")
        params.append(item_code)
    if model_name:
        where.append("model_name = ?")
        params.append(model_name)
    df = st.df(
        f"""SELECT target_week, model_name, scope, city_code, item_code, mase, {mase_rw_expr},
                   smape, mae, coverage_80, bias, n_obs, is_backtest
            FROM {st.scan('metrics')} WHERE {' AND '.join(where)}
            ORDER BY target_week DESC, model_name LIMIT {int(limit)}""",
        params,
    )
    rows = [
        ScorecardRow(
            target_week=_as_date(r["target_week"]), model_name=r["model_name"],
            scope=r["scope"], city_code=r.get("city_code"), item_code=r.get("item_code"),
            mase=_f(r["mase"]), mase_rw=_f(r.get("mase_rw")), smape=_f(r["smape"]),
            mae=_f(r["mae"]), coverage_80=_f(r["coverage_80"]), bias=_f(r["bias"]),
            n_obs=int(r["n_obs"]), is_backtest=bool(r["is_backtest"]),
        )
        for r in df.to_dict("records")
    ]
    return ListResponse[ScorecardRow](data=rows, meta=_meta())


@app.get("/api/drift", response_model=ListResponse[DriftRow], tags=["accuracy"])
def drift(since: dt.date | None = None, severity: str | None = None,
          limit: int = Query(200, ge=1, le=2000)):
    st = S.store()
    if not st.has("drift"):
        return ListResponse[DriftRow](data=[], meta=_meta())
    where, params = ["1=1"], []
    if since:
        where.append("checked_on >= ?")
        params.append(since)
    if severity:
        where.append("severity = ?")
        params.append(severity)
    df = st.df(
        f"""SELECT checked_on, channel, subject, test, statistic, threshold, fired,
                   severity, note
            FROM {st.scan('drift')} WHERE {' AND '.join(where)}
            ORDER BY checked_on DESC, fired DESC LIMIT {int(limit)}""",
        params,
    )
    rows = [
        DriftRow(
            checked_on=_as_date(r["checked_on"]), channel=r["channel"], subject=r["subject"],
            test=r["test"], statistic=_f(r["statistic"]), threshold=_f(r["threshold"]),
            fired=bool(r["fired"]), severity=r["severity"], note=r["note"],
        )
        for r in df.to_dict("records")
    ]
    return ListResponse[DriftRow](data=rows, meta=_meta())


@app.get("/api/model", tags=["accuracy"])
def model():
    """The registry JSON plus the promotion log, rendered verbatim on /model."""
    st = S.store()
    reg = st.registry()
    if not reg:
        raise ApiError("NOT_FOUND", "no model registry found", status=404)
    return {"data": reg, "meta": _meta().model_dump()}


@app.get("/api/download/panel.parquet", tags=["dataset"])
def download_parquet():
    return RedirectResponse(S.DATASET_RELEASE_URL, status_code=302)


@app.get("/api/download/panel.csv", tags=["dataset"])
def download_csv(
    city_code: str | None = None,
    item_code: str | None = None,
    from_: dt.date | None = Query(None, alias="from"),
    to: dt.date | None = None,
):
    st = S.store()
    where, params = ["1=1"], []
    for col, val in (("city_code", city_code), ("item_code", item_code)):
        if val:
            where.append(f"{col} = ?")
            params.append(val)
    if from_:
        where.append("week_ending >= ?")
        params.append(from_)
    if to:
        where.append("week_ending <= ?")
        params.append(to)
    df = st.df(
        f"""SELECT week_ending, city_code, city_en, item_code, item_en, unit_raw, unit_norm,
                   qty_norm, price_min, price_avg, price_max, price_per_unit, revision,
                   source, source_url
            FROM {st.scan('prices_weekly')} WHERE {' AND '.join(where)}
            ORDER BY week_ending, city_code, item_code""",
        params,
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    name = "bhao_panel"
    if city_code:
        name += f"_{city_code}"
    if item_code:
        name += f"_{item_code}"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


@app.get("/", include_in_schema=False)
def root():
    m = S.store().meta()
    return {
        "name": "Bhao API",
        "docs": "/api-docs",
        "openapi": "/api/openapi.json",
        "panel_week": m.get("panel_week"),
        "is_fixture": m.get("is_fixture"),
    }
