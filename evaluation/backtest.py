"""Rolling-origin backtest harness (10-EVALUATION.md, frozen protocol).

    fold i: made_on = W - (K - i) weeks; train = as_of(panel, made_on);
            target_week = made_on + 7 days; predict, score.

Every fold trains through as_of() — revision-aware. No random splits, ever.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from contracts.schemas import as_of


@dataclass
class Fold:
    index: int
    made_on: dt.date
    target_week: dt.date
    train: pd.DataFrame = field(repr=False, default=None)
    eval: pd.DataFrame = field(repr=False, default=None)


def week_seq(start: dt.date, n: int) -> list[dt.date]:
    return [start + dt.timedelta(weeks=i) for i in range(n)]


def make_folds(panel: pd.DataFrame, n_folds: int = 12, min_train_weeks: int = 26) -> list[Fold]:
    """Build K folds ending at the panel's last week. Reduces K rather than
    pretending when the panel is short (R3 in 12-RISKS.md)."""
    weeks = sorted(set(pd.to_datetime(panel["week_ending"]).dt.date))
    assert weeks, "empty panel"
    W = weeks[-1]
    k = n_folds
    while k > 1 and (W - dt.timedelta(weeks=k - 1 + min_train_weeks)) < weeks[0]:
        k -= 1

    folds: list[Fold] = []
    for i in range(1, k + 1):
        made_on = W - dt.timedelta(weeks=k - i + 1)  # fold K: made_on = W-1wk, target = W
        target_week = made_on + dt.timedelta(weeks=1)
        train = as_of(panel, made_on)
        eval_rows = panel[
            (pd.to_datetime(panel["week_ending"]).dt.date == target_week) & (panel["revision"] == 0)
        ].copy()
        folds.append(
            Fold(index=i, made_on=made_on, target_week=target_week, train=train, eval=eval_rows)
        )
    return folds
