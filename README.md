# Bhao — بھاؤ

**What things cost in Pakistan, weekly — and what they'll cost next week.**

> ⚠ **Work in progress.** This README skeleton is Phase 0 scaffolding; the sections
> below are filled in as each track lands. No number appears here until it exists in
> `metrics.parquet` — that rule is the project's personality.

Bhao scrapes the Pakistan Bureau of Statistics weekly retail price survey, turns it
into the tidy panel nobody publishes, forecasts next week's price for every
city × commodity pair with honest prediction intervals, detects when its own accuracy
degrades, retrains and re-promotes itself, and serves all of it through a bilingual
Urdu/English web app, a public API, and an open dataset — alongside a scorecard of
every forecast it has ever gotten wrong.

## Status

| Track | Phase | What's there |
|---|---|---|
| A — ingest | 0 done | contracts (schemas, enums, fixtures) |
| B — model | 0 done | reading; leakage test first |
| C — serve | 0 done | scaffolding: pyproject, Makefile, CI, README |

## Results

<!-- Filled by Track B from metrics.parquet. Baseline vs model, MASE / sMAPE /
     coverage, from the real backtest. Never estimate a number into this table. -->

## The data problem

<!-- Why this data is hard: merged cells, three header rows, 17 cities as vertical
     blocks of seven, `Islamabad (01)`, units as free text, filename drift. -->

## Architecture

```
PBS weekly xlsx ─▶ ingest (A) ─▶ data/panel/*.parquet ─▶ features/models/eval/drift (B)
                                            │                       │
                                            └──▶ api (C) ◀── data/forecasts + registry (B)
                                                     │
                                                     ▼
                                        web (Next.js, bilingual) · public dataset
```

## Drift and retraining

<!-- A real fired example goes here once one exists. Never simulate. -->

## How to run

```bash
make install        # python 3.11 venv + deps
make fixtures       # regenerate the deterministic fixture set
make test           # pytest
make api            # FastAPI on :8000
make web            # Next.js on :3000
docker compose -f docker/compose.yml up   # both + data volume
```

## API reference

<!-- Every route in 03-CONTRACTS.md Contract 3; auto-documented at /api-docs. -->

## Dataset download and citation

<!-- panel.parquet / panel.csv from a GitHub Release; citation line. -->

## Limitations

<!-- h=1 only · coverage is what PBS surveyed · panel starts where the archive
     starts · no causal claims · not advice · revisions exist · WFP is not ours. -->

## Licence

MIT. Data: Pakistan Bureau of Statistics (public official statistics, attributed per
row) and WFP/HDX (used under its own licence, labelled as an existing dataset).
