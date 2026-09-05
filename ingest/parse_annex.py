"""parse_annex — the hard parse: 17 cities laid out as vertical blocks of 7,
each city 3 columns (MIN/AVG/MAX), city headers as `Islamabad (01)`,
merged cells everywhere, numbers as strings, `-` meaning not-surveyed.

Structure (verified on the real 2026-08-27 file by the spike):
  row 3:   city header row — `Name (NN)` in cols D, G, J, M, P, S, V (blocks 1-2)
  row 4:   NO. / DESCRIPTION / UNIT / MIN / AVG / MAX × 7
  row 5:   column numbers (1..24)
  row 6:   'PRICES ON DD-MM-YYYY' banner
  row 7+:  item rows: A=sr, B=item name, C=unit, D..X = 7 cities × 3
  block 2: header row 61, items from row 65, cities 08-14
  block 3: header row 119 — Bannu (15), Quetta (16), Khuzdar (17) at D/G/J;
           cols M.. hold PBS's national-average columns (skipped; Page 2 has them)

Nothing is hardcoded by row: blocks are found by scanning every cell for the
`(NN)` city-header regex. Assertions fail the run loudly rather than publishing a
wrong panel (05-TRACK-A-INGEST.md).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import openpyxl

from ingest.normalise import coerce_number

CITY_HEADER_RE = re.compile(r"^(?P<name>[A-Za-z\s\.\-'/]+?)\s*\((?P<code>\d{2})\)$")

N_CITIES_EXPECTED = (15, 20)  # loud-fail band
N_ITEMS_EXPECTED = (40, 80)


@dataclass
class CityCell:
    code: str
    name: str
    row: int
    col: int  # 1-based column of the MIN column of this city's triple


@dataclass
class AnnexRow:
    sr: int
    item_raw: str
    unit_raw: str
    city_code: str
    price_min: float | None
    price_avg: float | None
    price_max: float | None


@dataclass
class ParsedAnnex:
    week_ending: dt.date | None = None
    cities: list[CityCell] = field(default_factory=list)
    rows: list[AnnexRow] = field(default_factory=list)
    sheet: str = "Appendix-A"
    source_url: str | None = None

    @property
    def city_codes(self) -> list[str]:
        seen = []
        for c in self.cities:
            if c.code not in seen:
                seen.append(c.code)
        return seen


def _iter_cells(ws):
    for row in ws.iter_rows():
        yield from row


def _find_city_cells(ws) -> list[CityCell]:
    found: list[CityCell] = []
    for cell in _iter_cells(ws):
        v = cell.value
        if isinstance(v, str):
            m = CITY_HEADER_RE.match(v.strip())
            if m:
                found.append(
                    CityCell(m.group("code"), m.group("name").strip(), cell.row, cell.column)
                )
    # merged city headers repeat the same code across blocks? No — codes are unique.
    return found


def _to_date_from_prices_banner(text: str) -> dt.date | None:
    m = re.search(r"(\d{1,2})[-\.](\d{1,2})[-\.](\d{4})", text or "")
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_annex(
    path,
    sheet: str = "Appendix-A",
    city_band: tuple[int, int] = N_CITIES_EXPECTED,
    item_band: tuple[int, int] = N_ITEMS_EXPECTED,
) -> ParsedAnnex:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        out = ParsedAnnex(sheet=sheet)
        out.cities = _find_city_cells(ws)
        n_cities = len(out.city_codes)
        assert (
            city_band[0] <= n_cities <= city_band[1]
        ), f"found {n_cities} city headers, expected {city_band}"

        # group cities by block (their header row)
        blocks: dict[int, list[CityCell]] = {}
        for c in out.cities:
            blocks.setdefault(c.row, []).append(c)
        for _blk_row, cities in blocks.items():
            cities.sort(key=lambda c: c.col)

        item_srs: dict[int, tuple[int, str, str]] = {}
        header_rows = sorted(blocks)

        for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_col=ws.max_column or 25), 1):
            r = row_idx
            if r in header_rows:
                continue
            # 'PRICES ON DD-MM-YYYY' banner carries the survey date
            for cell in row[:6]:
                if isinstance(cell.value, str) and "PRICES ON" in cell.value.upper():
                    d = _to_date_from_prices_banner(cell.value)
                    if d and out.week_ending is None:
                        out.week_ending = d

            if not row or len(row) < 4:
                continue
            sr_v, name_v, unit_v = row[0].value, row[1].value, row[2].value
            # an item row: numeric sr in col A, non-empty name in B, unit in C
            sr = coerce_number(sr_v)
            if sr is None or sr != int(sr):
                continue
            if not isinstance(name_v, str) or not name_v.strip():
                continue
            if not isinstance(unit_v, str) or not unit_v.strip():
                continue
            if CITY_HEADER_RE.match(name_v.strip()):
                continue
            sr_i = int(sr)
            item_srs.setdefault(sr_i, (sr_i, name_v.strip(), unit_v.strip()))

            for city in blocks[max(br for br in header_rows if br <= r)]:
                base = city.col - 1  # 0-based index of this city's MIN column
                triple = row[base : base + 3]
                if len(triple) < 3:
                    continue
                pmin = coerce_number(triple[0].value)
                pavg = coerce_number(triple[1].value)
                pmax = coerce_number(triple[2].value)
                # `-` AND a printed 0 both mean "no quote" — PBS prints 0.00 for
                # not-surveyed cells in some months (verified: Rice IRRI-6 in
                # Gujranwala/Sialkot/Lahore, Oct 2025 - Jan 2026). A price of
                # Rs 0 does not exist; null it like "-".
                if (pmin, pavg, pmax) == (0.0, 0.0, 0.0) or pavg == 0:
                    pmin = pavg = pmax = None
                # `-` means not surveyed → all three None; row kept
                if pmin is None and pavg is None and pmax is None:
                    out.rows.append(
                        AnnexRow(sr_i, name_v.strip(), unit_v.strip(), city.code, None, None, None)
                    )
                    continue
                assert pavg is not None, (
                    f"avg missing while min/max present at sheet row {r}, "
                    f"city {city.code}, item {name_v!r}"
                )
                # min <= avg <= max where all present: violations are dropped, loudly
                if (pmin is not None and pmin > pavg) or (pmax is not None and pmax < pavg):
                    raise AssertionError(
                        f"min<=avg<=max violated at sheet row {r}, city {city.code}, "
                        f"item {name_v!r}: {pmin}, {pavg}, {pmax}"
                    )
                out.rows.append(
                    AnnexRow(sr_i, name_v.strip(), unit_v.strip(), city.code, pmin, pavg, pmax)
                )

        n_items = len(item_srs)
        assert (
            item_band[0] <= n_items <= item_band[1]
        ), f"found {n_items} item rows, expected {item_band}"
        assert out.week_ending is not None, "no 'PRICES ON DD-MM-YYYY' banner found in annex"
        return out
    finally:
        wb.close()
