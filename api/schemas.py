"""Pydantic response models — Contract 3, exactly. They generate the OpenAPI schema
the frontend types itself from, so there is one source of truth and no drift."""

from __future__ import annotations

import datetime as dt
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

Lang = Literal["en", "ur"]
Direction = Literal["up", "down", "flat"]

T = TypeVar("T")


class Meta(BaseModel):
    generated_at: dt.datetime
    panel_week: dt.date | None = None
    model_version: str | None = None
    is_fixture: bool = False
    rows: int | None = None
    forecast_run_id: str | None = None


class ListResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    panel_week: dt.date | None
    forecast_run_id: str | None
    model_version: str | None
    rows: int | None
    uptime_s: int
    is_fixture: bool
    panel_age_days: int | None = None


class City(BaseModel):
    city_code: str
    city_en: str
    city_ur: str
    province_en: str
    province_ur: str
    n_items: int


class Item(BaseModel):
    item_code: str
    item_en: str
    item_ur: str
    unit_raw: str
    unit_norm: str
    qty_norm: float
    category: str
    is_food: bool
    is_administered: bool


class PricePoint(BaseModel):
    week_ending: dt.date
    city_code: str
    item_code: str
    price_min: float | None
    price_avg: float | None
    price_max: float | None
    price_per_unit: float | None
    revision: int
    source_url: str


class HistoryPoint(BaseModel):
    week_ending: dt.date
    price_avg: float | None


class RecentError(BaseModel):
    mase: float | None
    mase_rw: float | None = None
    mae: float | None = None
    n_weeks: int


class Forecast(BaseModel):
    city_code: str
    item_code: str
    item_en: str
    item_ur: str
    city_en: str
    city_ur: str
    unit_raw: str
    target_week: dt.date | None
    p10: float | None
    p50: float | None
    p90: float | None
    last_actual: float | None
    last_actual_week: dt.date | None
    direction: Direction
    pct_change_expected: float | None
    model_version: str | None
    made_on: dt.date | None
    history: list[HistoryPoint]
    recent_error: RecentError


class Mover(BaseModel):
    item_code: str
    item_en: str
    item_ur: str
    price_avg: float | None
    pct_change: float | None
    rank: int


class ScorecardRow(BaseModel):
    target_week: dt.date
    model_name: str
    scope: str
    city_code: str | None = None
    item_code: str | None = None
    mase: float | None
    mase_rw: float | None = None
    smape: float | None
    mae: float | None
    coverage_80: float | None
    bias: float | None
    n_obs: int
    is_backtest: bool


class DriftRow(BaseModel):
    checked_on: dt.date
    channel: str
    subject: str
    test: str
    statistic: float | None
    threshold: float | None
    fired: bool
    severity: str
    note: str
