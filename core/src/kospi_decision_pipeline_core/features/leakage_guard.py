from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date


class LeakageError(ValueError):
    pass


def assert_no_forbidden_columns(
    columns: Iterable[str],
    forbidden_prefixes: tuple[str, ...] = ("target_", "future_"),
) -> None:
    forbidden = [column for column in columns if column.startswith(forbidden_prefixes)]
    if forbidden:
        raise LeakageError(f"forbidden columns detected: {forbidden}")


def assert_trailing_window(
    values: Sequence[float],
    current_index: int,
    window_size: int,
    *,
    window_bounds: tuple[int, int] | None = None,
) -> None:
    if current_index < 0 or current_index >= len(values):
        raise LeakageError("current_index must reference an existing observation")
    if window_size <= 0:
        raise LeakageError("window_size must be positive")

    expected_start = current_index - window_size + 1
    expected_end = current_index
    if expected_start < 0:
        raise LeakageError("trailing window requires sufficient history")

    start_idx, end_idx = (expected_start, expected_end) if window_bounds is None else window_bounds
    if end_idx > current_index:
        raise LeakageError("trailing window cannot reference future indices")
    if start_idx != expected_start or end_idx != expected_end:
        raise LeakageError(
            "trailing window must exactly equal "
            + f"[{expected_start}, {expected_end}] for current_index={current_index}"
        )


def assert_not_full_period_normalized(
    series_stats: Mapping[str, float],
    window_stats: Mapping[str, float],
    tol: float = 1e-9,
) -> None:
    missing_keys = sorted(set(series_stats) ^ set(window_stats))
    if missing_keys:
        raise LeakageError(f"missing statistic keys: {missing_keys}")

    if all(abs(window_stats[key] - series_stats[key]) <= tol for key in series_stats):
        raise LeakageError(
            "full-period normalization detected: window_stats match full-period stats"
        )


def assert_join_not_from_future(*, joined_as_of: date, decision_date: date) -> None:
    if joined_as_of > decision_date:
        raise LeakageError(
            "future-join walk-forward rows must satisfy joined_as_of <= decision_date"
        )


__all__ = [
    "LeakageError",
    "assert_join_not_from_future",
    "assert_no_forbidden_columns",
    "assert_not_full_period_normalized",
    "assert_trailing_window",
]
