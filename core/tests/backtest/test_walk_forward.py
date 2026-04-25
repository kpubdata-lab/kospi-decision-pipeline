from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from importlib import import_module
from typing import Protocol, cast

import pytest

_walk_forward = import_module("kospi_decision_pipeline_core.backtest.walk_forward")


class _WalkForwardFoldCtor(Protocol):
    def __call__(
        self,
        *,
        fold_id: int,
        train_cutoff: date,
        train_indices: tuple[int, ...],
        test_indices: tuple[int, ...],
    ) -> object: ...


class _WalkForwardSplitterInstance(Protocol):
    def split(self, trade_dates: Sequence[date]) -> Iterator[object]: ...


class _WalkForwardSplitterCtor(Protocol):
    def __call__(
        self,
        *,
        min_train_rows: int = 252,
        test_fold_size: int = 20,
        gap_days: int = 0,
    ) -> _WalkForwardSplitterInstance: ...


WalkForwardFold = cast(_WalkForwardFoldCtor, getattr(_walk_forward, "WalkForwardFold"))
WalkForwardSplitter = cast(_WalkForwardSplitterCtor, getattr(_walk_forward, "WalkForwardSplitter"))


def _trade_dates(count: int) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def test_walk_forward_splitter_yields_expanding_window_folds_with_final_partial() -> None:
    trade_dates = _trade_dates(313)

    folds = list(WalkForwardSplitter().split(trade_dates))

    assert folds == [
        WalkForwardFold(
            fold_id=1,
            train_cutoff=trade_dates[251],
            train_indices=tuple(range(252)),
            test_indices=tuple(range(252, 272)),
        ),
        WalkForwardFold(
            fold_id=2,
            train_cutoff=trade_dates[271],
            train_indices=tuple(range(272)),
            test_indices=tuple(range(272, 292)),
        ),
        WalkForwardFold(
            fold_id=3,
            train_cutoff=trade_dates[291],
            train_indices=tuple(range(292)),
            test_indices=tuple(range(292, 312)),
        ),
        WalkForwardFold(
            fold_id=4,
            train_cutoff=trade_dates[311],
            train_indices=tuple(range(312)),
            test_indices=(312,),
        ),
    ]


def test_walk_forward_splitter_respects_gap_days() -> None:
    trade_dates = _trade_dates(254)

    folds = list(WalkForwardSplitter(test_fold_size=1, gap_days=1).split(trade_dates))

    assert folds == [
        WalkForwardFold(
            fold_id=1,
            train_cutoff=trade_dates[251],
            train_indices=tuple(range(252)),
            test_indices=(253,),
        )
    ]


def test_walk_forward_splitter_raises_when_test_row_date_is_not_strictly_greater() -> None:
    trade_dates = _trade_dates(252)
    trade_dates.append(trade_dates[-1])

    with pytest.raises(
        ValueError,
        match="^test row date must be strictly greater than train_cutoff$",
    ):
        _ = list(WalkForwardSplitter(test_fold_size=1).split(trade_dates))


def test_walk_forward_splitter_yields_no_folds_when_rows_are_insufficient() -> None:
    assert list(WalkForwardSplitter().split(_trade_dates(251))) == []
