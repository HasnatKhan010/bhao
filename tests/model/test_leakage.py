"""THE leakage test. Written before any model exists (06-TRACK-B-MODEL.md, Phase 0).

Leakage via revisions is the most likely serious bug in this project: a restated
price published *after* a fold's made_on is not knowable at forecast time, and
training on it makes every metric look good while being false.

These tests exercise the fold generator's contract directly:
  - no fold's training set contains a row with week_ending > made_on
  - no fold's training set contains a revision row that became known after made_on
  - the fold's evaluation target is exactly made_on + 7 days
  - folds never shuffle, never overlap test with training
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from contracts.schemas import as_of
from evaluation.backtest import make_folds


def _panel(n_weeks: int = 60) -> pd.DataFrame:
    """A tiny panel with a planted post-hoc revision in the middle."""
    weeks = [dt.date(2026, 1, 1) + dt.timedelta(weeks=i) for i in range(n_weeks)]
    rows = []
    for i, w in enumerate(weeks):
        for city in ("05", "10"):
            rows.append({
                "week_ending": w,
                "city_code": city,
                "item_code": "019",
                "price_avg": 100.0 + i + (5 if city == "10" else 0),
                "ingested_at": pd.Timestamp(w + dt.timedelta(days=2), tz="UTC"),  # Friday publication
                "revision": np.int32(0),
            })
            # planted restatement: week 30's price restated 3 weeks after publication
            # (revision 0 keeps the ORIGINAL price; revision 1 carries the restatement)
            if i == 30:
                rows.append({
                    "week_ending": w,
                    "city_code": city,
                    "item_code": "019",
                    "price_avg": 160.0 + (5 if city == "10" else 0),  # restated: +30 over the original
                    "ingested_at": pd.Timestamp(w + dt.timedelta(days=2 + 21), tz="UTC"),
                    "revision": np.int32(1),
                })
    return pd.DataFrame(rows).astype({"revision": "int32"})


class TestFoldDiscipline:
    def test_no_future_weeks_in_training(self):
        panel = _panel()
        for fold in make_folds(panel, n_folds=8):
            train = fold.train
            weeks = pd.to_datetime(train["week_ending"]).dt.date
            assert (weeks <= fold.made_on).all(), (
                f"fold made_on={fold.made_on} trained on week {weeks.max()}"
            )

    def test_no_revision_known_after_made_on(self):
        panel = _panel()
        restated_week = dt.date(2026, 1, 1) + dt.timedelta(weeks=30)
        for fold in make_folds(panel, n_folds=8):
            train = fold.train
            seen = train[(train["week_ending"] == restated_week)]
            if fold.made_on <= restated_week + dt.timedelta(days=23):
                # the restatement (ingested +21d after the Friday publication) is
                # NOT knowable yet — every visible row must be revision 0
                assert (seen["revision"] == 0).all(), (
                    f"fold made_on={fold.made_on} saw the restatement early"
                )
        # and after it lands, as_of picks the restated value
        late_fold = [f for f in make_folds(panel, n_folds=8) if f.made_on > restated_week + dt.timedelta(days=23)][0]
        seen = late_fold.train[late_fold.train["week_ending"] == restated_week]
        assert (seen["revision"] == 1).all()

    def test_target_is_exactly_one_week_ahead(self):
        for fold in make_folds(_panel(), n_folds=6):
            assert (fold.target_week - fold.made_on).days == 7

    def test_folds_are_ordered_and_expanding(self):
        folds = make_folds(_panel(), n_folds=6)
        made = [f.made_on for f in folds]
        assert made == sorted(made)
        sizes = [len(f.train) for f in folds]
        assert sizes == sorted(sizes), "expanding window: each fold trains on more data"

    def test_train_has_one_row_per_key(self):
        for fold in make_folds(_panel(), n_folds=6):
            assert fold.train.groupby(["week_ending", "city_code", "item_code"]).size().eq(1).all()

    def test_eval_rows_are_the_target_week_only(self):
        for fold in make_folds(_panel(), n_folds=6):
            weeks = pd.to_datetime(fold.eval["week_ending"]).dt.date.unique()
            assert list(weeks) == [fold.target_week]


class TestAsOfGroundTruth:
    """The fixture's planted revision must be invisible before it lands — the
    exact leak these tests exist to catch."""

    def test_planted_revision_invisible_then_visible(self):
        panel = _panel()
        wk = dt.date(2026, 1, 1) + dt.timedelta(weeks=30)
        before = as_of(panel, wk + dt.timedelta(days=7))
        after = as_of(panel, wk + dt.timedelta(days=30))
        b = before[(before["week_ending"] == wk)]
        a = after[(after["week_ending"] == wk)]
        # revision 0 = original (~130 for city 10); revision 1 = restated (+30)
        assert int(b["revision"].iloc[0]) == 0
        assert float(b["price_avg"].iloc[0]) == 130.0
        assert int(a["revision"].iloc[0]) == 1
        assert float(a["price_avg"].iloc[0]) == 160.0
