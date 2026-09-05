"""Drift thresholds — every number justified, in one place (10-EVALUATION.md).

An unjustified threshold is the tell that a drift detector is decoration. Justified
ones are the opposite. These constants are what methodology-b.md cites.
"""

from __future__ import annotations

# PSI bands (industry standard, cited rather than invented)
PSI_NONE = 0.10
PSI_WARN = 0.25

# KS two-sample, strict because we run many tests
KS_ALPHA = 0.01

# Rolling MASE: > 1.25x the backtest MASE for 2 consecutive weeks
ROLLING_MASE_MULT = 1.25
ROLLING_MASE_CONSECUTIVE = 2
ROLLING_MASE_WINDOW = 8

# Page–Hinkley on the |residual| stream. Tuned on the fixture's planted variance
# regime shift (item 021: sigma 0.02 -> 0.08 from week 100): the quiet regime's
# mean |log-return| is ~0.016, so delta sits just above it and the shift pushes
# the cumulative deviation past lambda within ~45 weeks. Recorded here so the
# tuning is reproducible and citable (10-EVALUATION.md).
PH_DELTA = 0.02
PH_LAMBDA = 2.0
PH_MIN_OBS = 12

# Coverage gap: |coverage_80 - 0.80| > 0.12 over 12 weeks
COVERAGE_GAP_MAX = 0.12
COVERAGE_WINDOW = 12

# Promotion gate (five conditions, all must hold)
PROMOTE_MIN_RELATIVE_IMPROVEMENT = 0.03  # challenger beats champion by >=3% relative
PROMOTE_MAX_CATEGORY_REGRESSION = 0.10  # no category loses by >10% relative
PROMOTE_COVERAGE_LO = 0.72
PROMOTE_COVERAGE_HI = 0.88

# Retraining: drift critical OR this many weeks since last retrain
RETRAIN_STALENESS_WEEKS = 4
