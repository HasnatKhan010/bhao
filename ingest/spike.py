"""Track A's one-hour spike, run against the real site (04-DATA-SOURCES.md §"verify first").

Run:  make spike   (or: python -m ingest.spike)

Items:
  1. Download this week's SPI-Report + Annex; print sheets, dims, first rows
  2. Find ALL city header rows by regex; confirm the count and correct block 3
  3. Confirm the item list and dump the exact unit strings
  4. Confirm Appendix-B geometry matches Appendix-A
  5. Read Page 1 and Page 3 of SPI-Report — what is in them?
  6. Pull two files a year apart and diff the item lists (how hard must pbs_aliases work?)
  7. Run the CDX query and count distinct retrievable Thursdays  ← highest value

Findings land in data/raw/spike_report.md and on stdout.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter

from ingest import config
from ingest.discover import all_known_weeks, download_report, find_report, latest_week
from ingest.fetch import cdx_query


def _last_completed_week(today: dt.date) -> dt.date:
    """The Thursday surveyed most recently (files publish on the following Friday)."""
    offset = (today.weekday() - 3) % 7  # 3 = Thursday
    return today - dt.timedelta(days=offset)


def _grid(ws, max_row: int, max_col: int) -> list[list]:
    rows = []
    for r, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True), 1
    ):
        rows.append(row)
        if r >= max_row:
            break
    return rows


def _find_city_headers(ws) -> list[tuple[int, str, str]]:
    """All cells matching `Name (NN)` — the (NN) suffix is the reliable signal."""
    found = []
    for row in ws.iter_rows(min_row=1, max_col=ws.max_column or 1):
        for cell in row:
            v = cell.value
            if isinstance(v, str):
                m = re.match(r"^(?P<name>[A-Za-z\s\.\-']+?)\s*\((?P<code>\d{2})\)$", v.strip())
                if m:
                    found.append((cell.row, m.group("name").strip(), m.group("code")))
    return found


def _item_rows(ws, name_col: str = "A") -> list[tuple[int, str, str]]:
    """(row, item name, unit) for rows that carry an item name and a unit column."""
    out = []
    for row in ws.iter_rows(min_row=1, values_only=False):
        name = row[0].value if len(row) else None
        unit = row[1].value if len(row) > 1 else None
        if isinstance(name, str) and name.strip() and not re.search(r"\(\d{2}\)$", name.strip()):
            out.append(
                (row[0].row, name.strip(), str(unit).strip() if isinstance(unit, str) else "")
            )
    return out


def main() -> None:
    lines: list[str] = []

    def say(s: str = "") -> None:
        lines.append(s)
        print(s)

    import openpyxl

    session = None
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    say("# Bhao ingest spike — findings")
    say(f"_Run at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}_")
    say()

    lw = latest_week(session)
    say(f"## 0. Latest live SPI week (sitemap): {lw}")

    target = lw or _last_completed_week(dt.date.today())
    say(f"## 1. Fetching week ending {target} ...")
    refs = find_report(target, session)
    if refs is None:
        say("**find_report failed** — falling back to the verified week 2026-08-20")
        target = dt.date(2026, 8, 20)
        refs = find_report(target, session)
    assert refs is not None, "could not discover any SPI week"
    say(f"- post: {refs.post_url}")
    say(f"- spi: {refs.spi_url}")
    say(f"- annex: {refs.annex_url}")
    say(f"- strategy: {refs.strategy}")

    paths = download_report(refs, session)
    say(f"- downloaded: {paths}")
    say()

    annex_path = paths["annex"]
    spi_path = paths["spi"]

    # ---------------- item 1: raw shapes ----------------
    if spi_path:
        wb = openpyxl.load_workbook(spi_path, read_only=True, data_only=True)
        say(f"## 1. SPI-Report sheets: {wb.sheetnames}")
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            say(f"- {sheet}: {ws.max_row} rows x {ws.max_column} cols")
        for probe in ("Page 1", "Page 3"):
            if probe in wb.sheetnames:
                ws = wb[probe]
                say(f"### {probe} first 4 rows:")
                for row in _grid(ws, 4, 8):
                    say(f"  {[str(v)[:28] if v is not None else '' for v in row]}")
        if "Page 2" in wb.sheetnames:
            ws = wb["Page 2"]
            say("### Page 2 first 8 rows:")
            for row in _grid(ws, 8, 9):
                say(f"  {[str(v)[:30] if v is not None else '' for v in row]}")
        wb.close()

    # ---------------- items 2-4: the annex ----------------
    if annex_path:
        wb = openpyxl.load_workbook(annex_path, read_only=True, data_only=True)
        say(f"## 2. Annex sheets: {wb.sheetnames}")
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            headers = _find_city_headers(ws)
            say(f"- {sheet}: {ws.max_row} rows x {ws.max_column} cols; {len(headers)} city headers")
            for r, name, code in headers:
                say(f"    row {r:>3}: {name} ({code})")
            items = _item_rows(ws)
            units = Counter(u for _, _, u in items)
            say(f"  {len(items)} item-ish rows; unit strings: {dict(units)}")
        wb.close()

    # ---------------- item 6: basket drift ----------------
    year_ago = target - dt.timedelta(weeks=52)
    say(f"## 6. Basket drift: comparing {target} vs {year_ago}")
    refs_ya = find_report(year_ago, session)
    if refs_ya:
        paths_ya = download_report(refs_ya, session)
        if paths_ya["annex"]:
            wb1 = openpyxl.load_workbook(annex_path, read_only=True, data_only=True)
            wb2 = openpyxl.load_workbook(paths_ya["annex"], read_only=True, data_only=True)
            if "Appendix-A" in wb1.sheetnames and "Appendix-A" in wb2.sheetnames:
                items_now = [n for _, n, _ in _item_rows(wb1["Appendix-A"])]
                items_then = [n for _, n, _ in _item_rows(wb2["Appendix-A"])]
                only_now = set(items_now) - set(items_then)
                only_then = set(items_then) - set(items_now)
                say(f"- items now: {len(items_now)}, a year ago: {len(items_then)}")
                say(f"- only in now: {sorted(only_now)[:10]}")
                say(f"- only in then: {sorted(only_then)[:10]}")
            wb1.close()
            wb2.close()
    say()

    # ---------------- item 7: the CDX ceiling ----------------
    say("## 7. Wayback CDX — how many distinct Thursdays exist? (the project ceiling)")
    weeks = set(all_known_weeks(session))
    for prefix in ("pbs.gov.pk/wp-content/uploads*spi*",):
        for row in cdx_query(prefix, extra="collapse=urlkey&limit=20000"):
            original = row.get("original", "")
            for m in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})", original):
                try:
                    d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                except ValueError:
                    continue
                if d.weekday() == 3:  # Thursdays
                    weeks.add(d)
    weeks = {w for w in weeks if w <= dt.date.today()}
    say(f"- **distinct Thursdays discoverable (sitemap + CDX): {len(weeks)}**")
    if weeks:
        say(f"- range: {min(weeks)} .. {max(weeks)}")
        by_year = Counter(w.year for w in weeks)
        say(f"- by year: {dict(sorted(by_year.items()))}")

    out = config.RAW_DIR / "spike_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
