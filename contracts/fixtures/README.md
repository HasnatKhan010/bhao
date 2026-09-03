# Bhao fixtures — the shared truth before real data exists

**These are synthetic.** Plausible, but obviously fake. Every number here was generated
by `make_fixtures.py`; nothing was observed. `model_registry.json` carries
`meta.is_fixture: true`, and the app shows a banner whenever it reads fixtures — a
fixture number must never be mistaken for a real one, and never screenshotted as one.

- **Seed: `20260824`** (plus `SEED+1` for missingness, `SEED+2` for partial rows,
  `SEED+3` for the national index, `SEED+4` for WFP, `SEED+5` for forecasts).
- **Panel: 17 cities × 51 SPI items × 156 weeks** ending Thursday 2026-08-20.
- Regenerate: `make fixtures` (or `python -m contracts.fixtures.make_fixtures`).
  Deterministic — re-running changes nothing.

## The nine planted pathologies

| # | Pathology | Where | What it catches |
|---|---|---|---|
| 1 | Ragged series start | items `024`, `040`, `042` begin 40 weeks late | B's lag features on short series |
| 2 | Missing cells | ~4% of rows have null prices (the real sheet prints `-`) | anything assuming a dense panel |
| 3 | Whole city missing | city `13` (Larkana) absent weeks 80–85 | C's chart gap rendering |
| 4 | Item renamed mid-series | item `004` has two `pbs_aliases` | the alias mechanism itself |
| 5 | A revision | `(2026-07-09, 05, 019)` has revision 0 **and** 1, ~3% apart | B's `as_of()` discipline — the leak test |
| 6 | Administered step change | petrol `047`: +18% in one week, flat 20 weeks either side | whether the model smears the step |
| 7 | Variance regime shift | potatoes `021`: weekly σ ×4 from week index 100 | B's drift detector — **it must fire** |
| 8 | Extreme scale spread | match box `044` ≈ Rs 2; gas charges `051` ≈ Rs 17,000 | why MASE and not RMSE |
| 9 | Unicode | real Urdu labels; item `033` contains a ZWNJ (`U+200C`) | naive `.encode()`, RTL rendering |

Each pathology has an asserting test in `tests/contracts/test_fixtures.py`, and every
fixture file validates against `contracts/schemas.py` (the executable contract).
