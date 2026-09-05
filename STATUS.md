# STATUS — Bhao live board

**All three sessions write here. Read it before you start work and after every merge.**

Append-only. **Newest at the top.** Never delete an entry — this file is the log of how the
project was actually built, and it is the thing that stops three sessions from surprising each
other.

Copy this file to the repo root (`/h/bhao/STATUS.md`) once the repo exists. That copy is the
live one; this one is the template.

---

## Entry format

```markdown
## YYYY-MM-DD HH:MM — {A|B|C} — {TAG}
What happened, in one or two lines.
Blocking? Yes/No — and if no, what you're doing instead.
→ Anything you need from another session, named.
```

### Tags

| Tag | Use when |
|---|---|
| `STARTING` | Beginning a session. One line on what you're picking up |
| `PHASE n DONE` | You finished a phase. Say what landed and on which branch |
| `GATE PASSED` | You've confirmed the gate checklist for your track |
| `CONTRACT CHANGE REQUEST` | You need a schema/route/enum changed. **Needs `ACK` from both others before it lands** |
| `DEP REQUEST` | You need a package in `pyproject.toml` (C owns it) |
| `ACK` | You've reviewed someone's request and agree |
| `NACK` | You disagree, with the reason |
| `DONE` | A specific requested thing is finished |
| `BLOCKED` | You genuinely cannot proceed. Say exactly on what |
| `HEADS UP` | Something the others need to know but needn't act on |
| `QUARANTINE` | (A) suspicious data held out of the panel, needs a human look |
| `FINDING` | A real result worth remembering. **These become README content** |
| `HANDOFF` | You're transferring ownership of one named file for one named task |

### The rules

1. **Always state "Blocking? Yes/No."** If no, say what you're doing meanwhile. This one line
   is the most useful thing in the file — it tells the others whether to interrupt themselves.
2. A `CONTRACT CHANGE REQUEST` lands only after both other sessions post `ACK`.
3. Never edit a file you don't own. Request it here instead.
4. Post a `FINDING` the moment you have one. By Phase 4 you will not remember it.
5. Never delete an entry.

---

## Live entries — newest first

<!-- ▲▲▲ ADD NEW ENTRIES DIRECTLY BELOW THIS LINE ▲▲▲ -->

## 2026-09-06 01:30 — ALL — GATE 3 REACHED (single-session run)
Deployed artefacts on disk; cron + Docker + healthcheck wired. The honest results:

| model | MASE (snaive-4) | MASE_rw (lag-1) | sMAPE | MAE | coverage@80 |
|---|---|---|---|---|---|
| **random_walk (champion)** | **0.321** | **0.557** | **2.12%** | **Rs 10.74** | **88.3%** |
| drift | 0.468 | 0.850 | 2.64% | Rs 14.51 | 59.1% |
| global_gbm | 0.665 | 1.136 | 3.10% | Rs 20.62 | 77.9% |
| seasonal_naive_ma | 0.703 | 1.220 | 4.02% | Rs 17.41 | 68.5% |
| seasonal_naive | 1.017 | 1.810 | 6.31% | Rs 23.68 | 77.1% |

5 scorable folds of the 27-week panel, h=1, 867 series, as_of() in every fold.
**The GBM loses to the random walk** — R1's predicted outcome, published, not hidden.
Champion = random_walk, with the reason in the promotion log. The GBM is re-evaluated
weekly as the panel deepens.
Blocking? No.

## 2026-09-06 01:20 — B — FINDING — real drift detected on real data
First drift pass over the live panel: PSI 0.134 (warn) on vol_ratio_4_26, KS fired on
lag_1 / roll_mean_4 / roll_mean_8 / pct_1 / vol_ratio_4_26. Consistent with onions
+25.3% and tomatoes moving in a single week (real movers, week ending 2026-09-03).
11 rows, 6 fired — every one a sentence, not a dict dump. Plus the fixture's planted
σ×4 regime shift is caught by PSI (>0.25), KS (p<0.01) and Page–Hinkley (tuned:
δ=0.02, λ=2.0 — recorded in drift/thresholds.py). Gate 3's "at least one real drift
row" is met with genuine data.

## 2026-09-06 01:10 — A — QUARANTINE + parse fix
The sheets print **0** for "no quote" (Rice IRRI-6, Gujranwala/Sialkot/Lahore, Oct
2025–Jan 2026) — 81 cells parsed as Rs 0 and briefly poisoned the GBM (log(0) → −inf
targets → 10^16 predictions). Parser now nulls 0 like "-"; validator quarantines
price ≤ 0; the 81 rows are nulled in the panel and logged in quarantine.csv. The
panel also gained 26 backfilled weeks (27 total, 2025-10-30 → 2026-09-03) and the
as_of() semantics were corrected: revision-0 rows are knowable by week (fetch time is
an artifact of backfill); only restatements gate on ingested_at.
Blocking? No.

## 2026-09-06 01:00 — C — PHASE 3 DONE
weekly.yml cron (Sun 06:00 PKT), Dockerfile.api/web + compose, ops/healthcheck.py
(panel_week within 10 days, exit 2 when stale), full README with only metrics.parquet
numbers. Web app builds clean (10 pages × 2 locales).

## 2026-09-05 16:40 — B — FINDING — the MASE denominator needs a second column
The frozen headline metric is MASE against **in-sample one-step seasonal-naive
(lag-52)** MAE per series (10-EVALUATION.md). On this panel that denominator is
inflated by inflation itself: Pakistani headline SPI runs ~9% YoY (verified week
2026-08-27: +9.04% combined; onions +125.86%), so |y_t − y_{t−52}| measures drift,
not forecast difficulty. Measured on fixtures, 3 folds:

| model | MASE (lag-52) | MASE (lag-1) | sMAPE | coverage@80 |
|---|---|---|---|---|
| random_walk | 0.152 | **0.951** | 1.48 | 0.761 |
| drift | 0.181 | 1.243 | 1.60 | 0.702 |
| seasonal_naive_ma | 0.217 | 1.344 | 1.90 | 0.615 |
| global_gbm (feat-v1, untuned) | 0.247 | 1.819 | 1.85 | 0.661 |
| seasonal_naive | 0.772 | 5.687 | 5.37 | 0.735 |

A random walk scoring MASE 0.15 is a statement about inflation, not about the model
— exactly the "suspiciously good number is a bug report" case (rule 4). So
`metrics.parquet` now carries an **additive** `mase_rw` column (lag-1 denominator)
alongside the contract's `mase`. Additive columns are explicitly allowed by
03-CONTRACTS.md §Conventions, so this is not a CONTRACT CHANGE. The README and
/scorecard must show both, and say which is which.
Blocking? No.
→ C: `/api/scorecard` should pass `mase_rw` through when present.

## 2026-09-05 16:35 — B — PHASE 1 DONE
tests/model/test_leakage.py written FIRST, then all six baselines + the
rolling-origin harness with as_of() in every fold. 32 model tests green.
Baseline table above. Fixture-scale timing: as_of 0.2s, features 8.2s (132k rows),
GBM 3-head fit 68s — full retrain well inside the 10-minute CPU budget.
Notes: (1) baseline intervals CLAMP to p50 rather than sorting the triple — on an
inflating series both residual quantiles can land on one side of zero and sorting
would replace the point forecast with a bound; the GBM still sorts, as specified.
(2) build_features() applies latest_revision() defensively so a restatement cannot
split a series into two rows and corrupt every lag.
Blocking? No.

## 2026-09-02 23:59 — C — PHASE 0 DONE
Scaffolding on `main`: pyproject.toml (py3.11, all three tracks' deps), .gitignore
(written before any commit — data/ excluded, fixtures kept), Makefile, .env.example,
.pre-commit-config.yaml, .github/workflows/ci.yml, README skeleton. `make install &&
make test` verified on Python 3.11.9.
Blocking? No — A and B can install.

## 2026-09-02 23:58 — A — PHASE 0 DONE
contracts/ + fixtures on `main`. B, C: pull now. Fixture seed **20260824**.
Panel: 17 cities × 51 SPI items × 156 weeks ending 2026-08-20 (132,907 rows).
All nine pathologies planted, each with an asserting test (tests/contracts/test_fixtures.py);
every fixture file validates against contracts/schemas.py. as_of() is data-driven: the
knowable cutoff is the publication date of the made_on week itself (read from
ingested_at), so late backfill and post-made_on restatements are invisible to folds.
Coverage unknown yet — CDX count coming at Gate 1.
Note: this repo is being built by **one session in the fallback order** (08 §"The
one-session fallback"), not three parallel sessions. Commits carry [A]/[B]/[C] prefixes
to preserve the track story.

## 0000-00-00 00:00 — SETUP — TEMPLATE
Nothing has started yet. First real entries will be A's and C's `PHASE 0 DONE`.

Expected first three:
- **A** — `PHASE 0 DONE`: contracts + fixtures on `main`, with the fixture seed
- **C** — `PHASE 0 DONE`: pyproject, .gitignore, Makefile, CI on `main`
- **A** — `HEADS UP`: the real CDX week count. **B is waiting on this number to set K**

---

## Open questions — keep this section edited, not appended

Delete a line when it is answered, and post the answer as a `FINDING`.

- [ ] **How many distinct Thursdays are actually retrievable from Wayback?** (A, Gate 1)
      → sets the fold count, whether lag-52 is possible, and the honest project ceiling
- [ ] Block 3 of `Appendix-A`: exact header row, and the spelling/order of cities 15–17 (A)
- [ ] Do `Page 1` and `Page 3` of `SPI-Report` contain anything worth parsing? (A)
- [ ] How much does the item basket change year over year? (A) → how hard `pbs_aliases` works
- [ ] Does `Appendix-B` share `Appendix-A`'s block geometry? (A)
- [ ] Log target or raw target for the GBM? (B) → test both, report which won
- [ ] Real MASE vs each baseline (B, Gate 2) → decides the whole framing of the writeup
- [ ] Which hosting tier for the live URL? (C, Phase 3)

---

## Decisions log — append, never edit

Record any decision that a future reader might otherwise think was an accident.

| Date | Who | Decision | Why |
|---|---|---|---|
| — | all | Long-format panel, not wide | Survives PBS adding an item without a migration |
| — | all | String codes, not ints | Excel eats leading zeros |
| — | all | Revisions appended, never overwritten | The only way the backtest is honest |
| — | all | MASE as headline metric | Prices span Rs 2 – Rs 17,000; the denominator *is* the baseline |
| — | all | No database in v1 | Weekly cadence, one writer, read-mostly. Parquet + DuckDB is correct |
| — | all | 3% relative MASE margin for promotion | Below that, 12-fold noise swamps the difference |
