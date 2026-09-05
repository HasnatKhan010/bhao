"""Publish — revision-aware append into data/panel/ (05-TRACK-A-INGEST.md).

Rules:
- New (week, city, item) → revision = 0.
- Existing key with a price differing beyond 0.01 → append revision = max+1.
  **Never edit an existing row.** Violating this would invalidate every metric
  in the project, silently and forever.
- Partition data/panel/prices_weekly/year=YYYY/ for DuckDB pruning, and maintain
  the consolidated data/panel/prices_weekly.parquet (the Contract 1 artefact).
- Write data/panel/_manifest.json: panel_week, n_rows, n_series, updated_at, sha256.

Item resolution: catalog aliases first; a genuinely new string mints a NEW code
(numeric order after the catalog) and is recorded in data/panel/item_aliases.json
plus a STATUS note — never fuzzy-matched into an existing series.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil

import pandas as pd

from contracts import item_catalog
from contracts.schemas import validate_frame
from ingest import config, normalise
from ingest.parse_annex import ParsedAnnex
from ingest.parse_spi import ParsedSPI

PRICE_COLS = ["price_min", "price_avg", "price_max"]


class ItemResolver:
    """Catalog aliases + a persisted dynamic-alias store for strings PBS adds later."""

    def __init__(self) -> None:
        self.dynamic: dict[str, dict] = {}
        if config.PANEL_DIR.joinpath("item_aliases.json").exists():
            self.dynamic = json.loads(
                config.PANEL_DIR.joinpath("item_aliases.json").read_text(encoding="utf-8")
            )

    def resolve(self, raw: str, unit_raw: str) -> tuple[str, bool]:
        """→ (item_code, is_new). A miss mints the next free code and persists it."""
        key = item_catalog.normalise_name(raw)
        if key in item_catalog.ALIAS_INDEX:
            return item_catalog.ALIAS_INDEX[key], False
        if key in self.dynamic:
            return self.dynamic[key]["item_code"], False

        used = set(item_catalog.ITEM_BY_CODE) | {v["item_code"] for v in self.dynamic.values()}
        new_code = f"{max(int(c) for c in used) + 1:03d}"
        self.dynamic[key] = {
            "item_code": new_code,
            "item_en": raw.strip(),
            "unit_raw": unit_raw,
        }
        self.save()
        log = config.RAW_DIR / "new_items.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(
                f"{dt.datetime.now(dt.UTC).isoformat(timespec='seconds')} NEW ITEM {raw!r} "
                f"-> {new_code} (unit {unit_raw!r}) — add an Urdu label in "
                f"contracts/item_labels_ur.csv and note in STATUS.md\n"
            )
        return new_code, True

    def metadata(self, code: str) -> dict:
        it = item_catalog.ITEM_BY_CODE.get(code)
        if it:
            return {
                "item_en": it.item_en,
                "unit_raw": it.unit_raw,
                "unit_norm": it.unit_norm,
                "qty_norm": it.qty_norm,
                "category": it.category,
                "spi_weight": it.spi_weight,
                "is_food": it.is_food,
                "is_administered": it.is_administered,
                "pbs_aliases": list(it.pbs_aliases),
                "item_ur": normalise.urdu_labels().get(it.item_en, it.item_en),
            }
        rec = next((v for v in self.dynamic.values() if v["item_code"] == code), None)
        if rec is None:
            raise KeyError(f"item code {code} unknown to catalog and dynamic store")
        unit_norm, qty_norm = normalise.parse_unit(rec["unit_raw"])
        return {
            "item_en": rec["item_en"],
            "unit_raw": rec["unit_raw"],
            "unit_norm": unit_norm,
            "qty_norm": qty_norm,
            "category": "other",
            "spi_weight": None,
            "is_food": False,
            "is_administered": False,
            "pbs_aliases": [rec["item_en"]],
            "item_ur": normalise.urdu_labels().get(rec["item_en"], rec["item_en"]),
        }

    def save(self) -> None:
        config.PANEL_DIR.mkdir(parents=True, exist_ok=True)
        (config.PANEL_DIR / "item_aliases.json").write_text(
            json.dumps(self.dynamic, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def annex_to_frame(annex: ParsedAnnex, resolver: ItemResolver) -> pd.DataFrame:
    """ParsedAnnex → contract-shaped (not yet validated) prices frame."""
    from ingest.parse_annex import ParsedAnnex as _PA  # noqa: F401 (typing only)

    rows = []
    ingested = pd.Timestamp.now(dt.UTC).floor("s")
    for r in annex.rows:
        code, _ = resolver.resolve(r.item_raw, r.unit_raw)
        meta = resolver.metadata(code)
        # the annex's own unit string is what the sheet printed for THIS item row
        unit_norm_r, qty_r = normalise.parse_unit(r.unit_raw)
        price_per_unit = round(r.price_avg / qty_r, 4) if r.price_avg is not None else None
        rows.append(
            {
                "week_ending": annex.week_ending,
                "city_code": r.city_code,
                "city_en": normalise.CITY_EN[r.city_code],
                "city_ur": normalise.CITY_UR[r.city_code],
                "item_code": code,
                "item_en": meta["item_en"],
                "item_ur": meta["item_ur"],
                "unit_raw": r.unit_raw,
                "unit_norm": unit_norm_r,
                "qty_norm": qty_r,
                "price_min": r.price_min,
                "price_avg": r.price_avg,
                "price_max": r.price_max,
                "price_per_unit": price_per_unit,
                "source": "pbs_spi_annex",
                "source_url": annex.source_url,
                "ingested_at": ingested,
                "revision": 0,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["qty_norm"] = df["qty_norm"].astype("float64")
    df["revision"] = df["revision"].astype("int32")
    df["ingested_at"] = df["ingested_at"].astype("datetime64[us, UTC]")
    return df


def spi_to_frame(
    spi: ParsedSPI, week_ending: dt.date, source_url: str, resolver: ItemResolver
) -> pd.DataFrame:
    """ParsedSPI → national_weekly rows (item '000' = the headline SPI index)."""
    ingested = pd.Timestamp.now(dt.UTC).floor("s")
    rows = []
    for r in spi.rows:
        if r.is_headline:
            code = "000"
        else:
            try:
                code, _ = resolver.resolve(r.item_raw, r.unit_raw)
            except Exception:
                continue  # national table rows without a resolvable name are logged elsewhere
        rows.append(
            {
                "week_ending": week_ending,
                "item_code": code,
                "price_this_week": r.price_this_week,
                "price_prev_week": r.price_prev_week,
                "price_same_week_last_year": r.price_same_week_last_year,
                "pct_change_wow": r.pct_change_wow,
                "pct_change_yoy": r.pct_change_yoy,
                "spi_weight_combined": None,
                "spi_weight_lowest_quintile": None,
                "source_url": source_url,
                "revision": 0,
                "ingested_at": ingested,
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["revision"] = df["revision"].astype("int32")
    df["ingested_at"] = df["ingested_at"].astype("datetime64[us, UTC]")
    for c in ("spi_weight_combined", "spi_weight_lowest_quintile"):
        df[c] = df[c].astype("float64")
    return df


def append_week(existing: pd.DataFrame, new_prices: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Revision-aware append. Returns (new panel, n_new_revision_rows).

    Idempotent: re-publishing a week whose values already match changes nothing.
    A value differing beyond 0.01 appends revision = max(existing)+1 — it never
    edits an existing row.
    """
    keys = ["week_ending", "city_code", "item_code"]

    if existing.empty:
        out = new_prices.copy()
        return out, 0

    # align dtypes so the merge/compare behaves: week_ending as object-of-date
    new_prices = new_prices.copy()
    new_prices["week_ending"] = new_prices["week_ending"].map(
        lambda v: v.date() if isinstance(v, dt.datetime) else v
    )
    existing = existing.copy()
    existing["week_ending"] = existing["week_ending"].map(
        lambda v: v.date() if isinstance(v, dt.datetime) else v
    )

    prev0 = existing[existing["revision"] == 0][keys + PRICE_COLS].rename(
        columns={c: f"prev_{c}" for c in PRICE_COLS}
    )
    merged = new_prices.merge(prev0, on=keys, how="left")

    # idempotency: every new row already present with matching values → no-op
    already = merged["prev_price_avg"].notna()
    if already.all():
        diffs = []
        for c in PRICE_COLS:
            d = (merged[c] - merged[f"prev_{c}"]).abs()
            diffs.append(d.where(merged[c].notna() & merged[f"prev_{c}"].notna(), 0).max())
        if max(diffs) <= 0.01:
            return existing, 0

    rev_by_key = {k: int(v) for k, v in existing.groupby(keys)["revision"].max().items()}
    revisions: list[int] = []
    for row in merged.itertuples(index=False):
        key = (row.week_ending, row.city_code, row.item_code)
        if pd.isna(row.prev_price_avg):
            revisions.append(0)
            continue
        diffs = [
            abs(getattr(row, c) - getattr(row, f"prev_{c}"))
            for c in PRICE_COLS
            if pd.notna(getattr(row, c)) and pd.notna(getattr(row, f"prev_{c}"))
        ]
        if diffs and max(diffs) > 0.01:
            revisions.append(rev_by_key.get(key, 0) + 1)
        else:
            revisions.append(0)
    merged["revision"] = pd.Series(revisions, dtype="int32")

    # keep only genuinely new rows (not already in the panel at the same revision)
    existing_keys = set(
        map(tuple, existing[keys + ["revision"]].itertuples(index=False, name=None))
    )
    keep = [
        i
        for i in merged.index
        if (
            merged.at[i, "week_ending"],
            merged.at[i, "city_code"],
            merged.at[i, "item_code"],
            int(merged.at[i, "revision"]),
        )
        not in existing_keys
    ]
    new_rows = merged.loc[keep, existing.columns.intersection(merged.columns)]
    out = pd.concat([existing, new_rows], ignore_index=True)
    for c in PRICE_COLS:
        out[c] = out[c].astype("float64")
    out["revision"] = out["revision"].astype("int32")
    out = out.sort_values(["week_ending", "city_code", "item_code", "revision"]).reset_index(
        drop=True
    )
    n_new_rev = int(len(new_rows[new_rows["revision"] > 0]))
    return out, n_new_rev


def write_panel(panel: pd.DataFrame) -> None:
    """Write the consolidated contract artefact + year partitions + manifest."""
    config.PANEL_DIR.mkdir(parents=True, exist_ok=True)
    consolidated = config.PANEL_DIR / "prices_weekly.parquet"
    panel.to_parquet(consolidated, index=False)

    part_dir = config.PANEL_DIR / "prices_weekly"
    if part_dir.exists():
        shutil.rmtree(part_dir)
    panel = panel.copy()
    panel["_year"] = pd.to_datetime(panel["week_ending"]).dt.year
    for year, sub in panel.groupby("_year"):
        ydir = part_dir / f"year={year}"
        ydir.mkdir(parents=True, exist_ok=True)
        sub.drop(columns=["_year"]).to_parquet(ydir / "part.parquet", index=False)

    weeks = sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))
    sha = hashlib.sha256(consolidated.read_bytes()).hexdigest()
    manifest = {
        "panel_week": weeks[-1].isoformat() if weeks else None,
        "n_rows": int(len(panel)),
        "n_series": int(panel.groupby(["city_code", "item_code"]).ngroups),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "sha256": sha,
    }
    (config.PANEL_DIR / "_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def write_national(national: pd.DataFrame) -> None:
    validate_frame(national, "national_weekly")
    national.to_parquet(config.PANEL_DIR / "national_weekly.parquet", index=False)


def write_items(panel: pd.DataFrame, resolver: ItemResolver) -> None:
    codes = sorted(panel["item_code"].unique())
    rows = []
    for code in codes:
        meta = resolver.metadata(code)
        sub = panel[panel["item_code"] == code]
        rows.append(
            {
                "item_code": code,
                "item_en": meta["item_en"],
                "item_ur": meta["item_ur"],
                "unit_raw": meta["unit_raw"],
                "unit_norm": meta["unit_norm"],
                "qty_norm": meta["qty_norm"],
                "category": meta["category"],
                "spi_weight": meta["spi_weight"],
                "is_food": meta["is_food"],
                "is_administered": meta["is_administered"],
                "pbs_aliases": meta["pbs_aliases"],
                "first_seen": pd.to_datetime(sub["week_ending"]).min().date(),
                "last_seen": pd.to_datetime(sub["week_ending"]).max().date(),
                "notes": None,
            }
        )
    df = pd.DataFrame(rows)
    df["qty_norm"] = df["qty_norm"].astype("float64")
    df["spi_weight"] = df["spi_weight"].astype("float64")
    df["is_food"] = df["is_food"].astype("bool")
    df["is_administered"] = df["is_administered"].astype("bool")
    validate_frame(df, "items")
    df.to_parquet(config.PANEL_DIR / "items.parquet", index=False)


def write_cities() -> None:
    from ingest.normalise import CITY_EN, CITY_LATLON, CITY_PROVINCE, CITY_UR

    rows = [
        {
            "city_code": code,
            "city_en": CITY_EN[code],
            "city_ur": CITY_UR[code],
            "province_en": CITY_PROVINCE[code][0],
            "province_ur": CITY_PROVINCE[code][1],
            "lat": CITY_LATLON[code][0],
            "lon": CITY_LATLON[code][1],
            "pbs_order": int(code) if code != "00" else 0,
        }
        for code in sorted(CITY_UR)
    ]
    df = pd.DataFrame(rows)
    df["pbs_order"] = df["pbs_order"].astype("int32")
    validate_frame(df, "cities")
    df.to_parquet(config.PANEL_DIR / "cities.parquet", index=False)


def load_panel() -> pd.DataFrame:
    path = config.PANEL_DIR / "prices_weekly.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
