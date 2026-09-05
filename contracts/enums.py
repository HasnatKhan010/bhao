"""Bhao enums — the literals everyone codes against.

Source of truth: 03-CONTRACTS.md §"Enums". Adding a member is a CONTRACT CHANGE
request in STATUS.md, never a unilateral edit.
"""

from __future__ import annotations

# Units after normalisation. `unit_norm` in prices_weekly.parquet / items.parquet.
UNIT_NORM = {
    "kg",
    "litre",
    "each",
    "dozen",
    "metre",
    "pair",
    "mmbtu",
    "kwh",
    "minute",
    "plate",
    "cup",
    "unit",
}

# Commodity categories.
CATEGORY = {
    "grains",
    "pulses",
    "cooking_oil",
    "dairy_eggs",
    "meat_poultry",
    "vegetables",
    "fruit",
    "sugar_sweeteners",
    "tea_beverages",
    "spices_condiments",
    "fuel_energy",
    "utilities",
    "household",
    "personal_care",
    "clothing_footwear",
    "services",
    "other",
}

# Provinces (city-level attribution).
PROVINCE = {
    "Punjab",
    "Sindh",
    "Khyber Pakhtunkhwa",
    "Balochistan",
    "Islamabad Capital Territory",
}

# Where a row came from.
SOURCE = {
    "pbs_spi_annex",
    "pbs_spi_national",
    "wfp_hdx",
}

# --- derived from Contract 2 prose; additive, validated, not replacements ---

# metrics.parquet `scope`.
SCOPE = {"overall", "city", "item", "city_item", "category", "administered"}

# drift.parquet `channel`.
DRIFT_CHANNEL = {"feature", "residual", "coverage", "schema"}

# drift.parquet `test`.
DRIFT_TEST = {"psi", "ks", "rolling_mase", "page_hinkley", "coverage_gap"}

# drift.parquet `severity`.
SEVERITY = {"info", "warn", "critical"}

# forecasts.parquet `model_name`.
MODEL_NAME = {
    "global_gbm",
    "seasonal_naive",
    "random_walk",
    "ets",
    "arima",
    "ensemble",
    "drift",
    "seasonal_naive_ma",
}

# --- cities ---

# PBS's own 17-city list (04-DATA-SOURCES.md). city_code "00" = national.
CITY_CODES = [f"{i:02d}" for i in range(0, 18)]


def validate(member_set: set[str], value: str, what: str) -> str:
    """Raise a loud error for an unrecognised enum value. Never default silently."""
    if value not in member_set:
        raise ValueError(f"unrecognised {what} {value!r}; expected one of {sorted(member_set)}")
    return value
