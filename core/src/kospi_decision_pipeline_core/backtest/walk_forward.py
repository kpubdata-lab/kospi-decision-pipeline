from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_id: int
    train_cutoff: date
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


class WalkForwardSplitter:
    _min_train_rows: int
    _test_fold_size: int
    _gap_days: int

    def __init__(
        self,
        *,
        min_train_rows: int = 252,
        test_fold_size: int = 20,
        gap_days: int = 0,
    ) -> None:
        self._min_train_rows = min_train_rows
        self._test_fold_size = test_fold_size
        self._gap_days = gap_days

    def split(self, trade_dates: Sequence[date]) -> Iterator[WalkForwardFold]:
        sorted_trade_dates = tuple(sorted(trade_dates))
        if len(sorted_trade_dates) <= self._min_train_rows + self._gap_days:
            return
        train_indices = tuple(range(self._min_train_rows))
        fold_id = 1
        while True:
            train_cutoff = sorted_trade_dates[train_indices[-1]]
            test_start = train_indices[-1] + 1 + self._gap_days
            if test_start >= len(sorted_trade_dates):
                return
            test_stop = min(test_start + self._test_fold_size, len(sorted_trade_dates))
            test_indices = tuple(range(test_start, test_stop))
            for test_index in test_indices:
                if sorted_trade_dates[test_index] <= train_cutoff:
                    raise ValueError("test row date must be strictly greater than train_cutoff")
            yield WalkForwardFold(
                fold_id=fold_id,
                train_cutoff=train_cutoff,
                train_indices=train_indices,
                test_indices=test_indices,
            )
            train_indices = (*train_indices, *test_indices)
            fold_id += 1
