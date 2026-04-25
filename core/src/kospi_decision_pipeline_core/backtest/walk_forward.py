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
        if min_train_rows <= 0:
            raise ValueError("min_train_rows must be positive")
        if test_fold_size <= 0:
            raise ValueError("test_fold_size must be positive")
        if gap_days < 0:
            raise ValueError("gap_days must be non-negative")
        self._min_train_rows = min_train_rows
        self._test_fold_size = test_fold_size
        self._gap_days = gap_days

    def split(self, trade_dates: Sequence[date]) -> Iterator[WalkForwardFold]:
        sorted_positions = tuple(sorted(range(len(trade_dates)), key=trade_dates.__getitem__))
        if len(sorted_positions) <= self._min_train_rows + self._gap_days:
            return
        train_positions = tuple(range(self._min_train_rows))
        fold_id = 1
        while True:
            train_cutoff = trade_dates[sorted_positions[train_positions[-1]]]
            test_start = train_positions[-1] + 1 + self._gap_days
            if test_start >= len(sorted_positions):
                return
            test_stop = min(test_start + self._test_fold_size, len(sorted_positions))
            test_positions = tuple(range(test_start, test_stop))
            for test_position in test_positions:
                if trade_dates[sorted_positions[test_position]] <= train_cutoff:
                    raise ValueError("test row date must be strictly greater than train_cutoff")
            yield WalkForwardFold(
                fold_id=fold_id,
                train_cutoff=train_cutoff,
                train_indices=tuple(sorted_positions[position] for position in train_positions),
                test_indices=tuple(sorted_positions[position] for position in test_positions),
            )
            train_positions = (*train_positions, *test_positions)
            fold_id += 1
