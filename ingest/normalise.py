"""Normalisation — unit parsing, number coercion, item resolution, Urdu labels.

One coercion function, used everywhere. Anything unmatched **raises** and gets a
STATUS.md note; never default to ("unit", 1.0) silently, never fuzzy-merge an item
(05-TRACK-A-INGEST.md).
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

from contracts import item_catalog
from contracts.enums import UNIT_NORM, validate as validate_enum

# ---------------------------------------------------------------------------
# numbers — the one coercion function
# ---------------------------------------------------------------------------

_NUM_STRIP_RE = re.compile(r"[,\s]|Rs\.?|%")
_BAD_TOKENS = {"-", "--", "", "n/a", "na", "nil", "none", "nan", "-"}


def coerce_number(v) -> float | None:
    """Coerce a spreadsheet cell to float. Non-numeric → None. Never float(x) bare.

    Handles: '171.55', '1,171.55', '-', '', 'N/A', ' 220 ', '+9.00%', 'Rs. 100'.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v != v:  # NaN
            return None
        return float(v)
    s = str(v).strip()
    if s.lower() in _BAD_TOKENS:
        return None
    s2 = _NUM_STRIP_RE.sub("", s)
    if not s2 or s2 in {"-", "."}:
        return None
    try:
        return float(s2)
    except ValueError:
        return None


def coerce_pct(v) -> float | None:
    """Percent as printed, e.g. '+9.00%' → 9.0, '-0.69' → -0.69."""
    n = coerce_number(v)
    return n


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------

# Raw PBS unit strings → (unit_norm, qty_norm). Extended as the parse meets new
# strings; an unmatched string raises (never defaults silently).
UNIT_MAP: dict[str, tuple[str, float]] = {
    "kg": ("kg", 1.0),
    "kgs": ("kg", 1.0),
    "gram": ("kg", 0.001),
    "grams": ("kg", 0.001),
    "litre": ("litre", 1.0),
    "ltr": ("litre", 1.0),
    "litres": ("litre", 1.0),
    "ltrs": ("litre", 1.0),
    "each": ("each", 1.0),
    "dozen": ("dozen", 1.0),
    "dz": ("dozen", 1.0),
    "mtr": ("metre", 1.0),
    "metre": ("metre", 1.0),
    "pair": ("pair", 1.0),
    "mmbtu": ("mmbtu", 1.0),
    "kwh": ("kwh", 1.0),
    "unit": ("unit", 1.0),
    "per unit": ("unit", 1.0),
    "minute": ("minute", 1.0),
    "per minute": ("minute", 1.0),
    "plate": ("plate", 1.0),
    "per plate": ("plate", 1.0),
    "cup": ("cup", 1.0),
    "per cup": ("cup", 1.0),
    "per litre": ("litre", 1.0),
    "per liter": ("litre", 1.0),
    "per kg": ("kg", 1.0),
    "suit": ("each", 1.0),
    "visit": ("each", 1.0),
}

_UNIT_QTY_RE = re.compile(
    r"^\s*(?P<qty>[\d\.]+)\s*(?P<unit>[A-Za-z\.]+)\s*(?P<rest>.*)$"
)


def parse_unit(raw: str) -> tuple[str, float]:
    """'20 Kg' → ('kg', 20.0); 'Per Litre' → ('litre', 1.0); 'MMBTU' → ('mmbtu', 1.0).

    Anything unmatched **raises** — a silent default would corrupt price_per_unit
    for every downstream consumer.
    """
    if raw is None:
        raise ValueError("unit string is None")
    s = str(raw).strip()
    s = s.replace("Rs.", "").strip()
    low = s.lower()

    direct = UNIT_MAP.get(low)
    if direct:
        return direct

    m = _UNIT_QTY_RE.match(s)
    if m:
        qty = float(m.group("qty"))
        unit_word = m.group("unit").lower().rstrip(".")
        base = UNIT_MAP.get(unit_word)
        if base and qty > 0:
            return (base[0], qty)

    # '1 Ltr' variants with the qty inside the word, e.g. '2.5Kg'
    m2 = re.match(r"^\s*([\d\.]+)\s*([a-zA-Z]+)\s*$", s)
    if m2:
        qty = float(m2.group(1))
        base = UNIT_MAP.get(m2.group(2).lower().rstrip("."))
        if base and qty > 0:
            return (base[0], qty)

    raise ValueError(
        f"unmatched unit string {raw!r}; extend UNIT_MAP and note it in STATUS.md"
    )


# ---------------------------------------------------------------------------
# items
# ---------------------------------------------------------------------------

def resolve_item(raw: str, alias_index: dict[str, str] | None = None) -> str:
    """Normalised alias lookup → item_code. A miss raises; callers may mint a NEW
    code (never a silent merge into an existing series)."""
    key = item_catalog.normalise_name(raw)
    idx = alias_index if alias_index is not None else item_catalog.ALIAS_INDEX
    if key in idx:
        return idx[key]
    raise KeyError(
        f"unmatched item string {raw!r} (normalised {key!r}); "
        "assign a new item_code and log it in STATUS.md"
    )


# ---------------------------------------------------------------------------
# Urdu labels — hand-curated (12-RISKS R9: machine translation is not allowed here)
# ---------------------------------------------------------------------------

_LABELS_CACHE: dict[str, str] | None = None


def urdu_labels() -> dict[str, str]:
    global _LABELS_CACHE
    if _LABELS_CACHE is None:
        path = Path(__file__).resolve().parent.parent / "contracts" / "item_labels_ur.csv"
        with path.open(encoding="utf-8") as f:
            _LABELS_CACHE = {row["item_en"]: row["item_ur"] for row in csv.DictReader(f)}
    return _LABELS_CACHE


# ---------------------------------------------------------------------------
# cities — PBS's own list; Urdu hand-curated
# ---------------------------------------------------------------------------

CITY_EN: dict[str, str] = {
    "00": "National",
    "01": "Islamabad",
    "02": "Rawalpindi",
    "03": "Gujranwala",
    "04": "Sialkot",
    "05": "Lahore",
    "06": "Faisalabad",
    "07": "Sargodha",
    "08": "Multan",
    "09": "Bahawalpur",
    "10": "Karachi",
    "11": "Hyderabad",
    "12": "Sukkur",
    "13": "Larkana",
    "14": "Peshawar",
    "15": "Bannu",
    "16": "Quetta",
    "17": "Khuzdar",
}

CITY_UR: dict[str, str] = {
    "01": "اسلام آباد",
    "02": "راولپنڈی",
    "03": "گوجرانوالہ",
    "04": "سیالکوٹ",
    "05": "لاہور",
    "06": "فیصل آباد",
    "07": "سرگودها",
    "08": "ملتان",
    "09": "بہاولپور",
    "10": "کراچی",
    "11": "حیدرآباد",
    "12": "سکھر",
    "13": "لاڑکانہ",
    "14": "پشاور",
    "15": "بنوں",
    "16": "کوئٹہ",
    "17": "خضدار",
    "00": "قومی",
}

CITY_PROVINCE: dict[str, tuple[str, str]] = {
    "01": ("Islamabad Capital Territory", "اسلام آباد دارالحکومت علاقہ"),
    "02": ("Punjab", "پنجاب"),
    "03": ("Punjab", "پنجاب"),
    "04": ("Punjab", "پنجاب"),
    "05": ("Punjab", "پنجاب"),
    "06": ("Punjab", "پنجاب"),
    "07": ("Punjab", "پنجاب"),
    "08": ("Punjab", "پنجاب"),
    "09": ("Punjab", "پنجاب"),
    "10": ("Sindh", "سندھ"),
    "11": ("Sindh", "سندھ"),
    "12": ("Sindh", "سندھ"),
    "13": ("Sindh", "سندھ"),
    "14": ("Khyber Pakhtunkhwa", "خیبر پختونخوا"),
    "15": ("Khyber Pakhtunkhwa", "خیبر پختونخوا"),
    "16": ("Balochistan", "بلوچستان"),
    "17": ("Balochistan", "بلوچستان"),
    "00": ("Pakistan (national)", "پاکستان (قومی)"),
}

CITY_LATLON: dict[str, tuple[float, float]] = {
    "01": (33.6844, 73.0479), "02": (33.5651, 73.0169), "03": (32.1877, 74.1945),
    "04": (32.4945, 74.5229), "05": (31.5204, 74.3587), "06": (31.4187, 73.0791),
    "07": (32.0836, 72.6711), "08": (30.1575, 71.5249), "09": (29.3956, 71.6836),
    "10": (24.8607, 67.0011), "11": (25.3960, 68.3578), "12": (27.7052, 68.8574),
    "13": (27.5589, 68.2123), "14": (34.0151, 71.5249), "15": (32.9887, 70.6056),
    "16": (30.1798, 66.9750), "17": (27.8006, 66.6258), "00": (None, None),
}


def week_ending_to_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def validate_unit_norm(u: str) -> str:
    return validate_enum(UNIT_NORM, u, "unit_norm")
