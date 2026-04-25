from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import cast

import kospi_decision_pipeline_core.features as features_package
import kospi_decision_pipeline_core.features.leakage_guard as leakage_guard_module
from kospi_decision_pipeline_core.features.agent_input import build_agent_feature_row
from kospi_decision_pipeline_core.features.leakage_guard import (
    LeakageError,
    assert_no_forbidden_columns,
    assert_not_full_period_normalized,
    assert_trailing_window,
)


@contextmanager
def _assert_raises(error_type: type[BaseException], match: str) -> Iterator[None]:
    try:
        yield
    except error_type as error:
        if match not in str(error):
            raise AssertionError(f"expected {match!r} in {error!r}") from error
    else:
        raise AssertionError(f"expected {error_type.__name__} to be raised")


def _join_walk_forward_row(
    *,
    decision_date: date,
    joined_as_of: date,
    row: Mapping[str, float | int | str],
) -> dict[str, float | int | str]:
    join_guard = cast(
        Callable[..., None],
        getattr(leakage_guard_module, "assert_join_not_from_future"),
    )
    join_guard(
        joined_as_of=joined_as_of,
        decision_date=decision_date,
    )
    return dict(row)


def _build_untyped_agent_feature_row(
    gold_row: Mapping[str, object],
    allowed_columns: tuple[str, ...],
) -> dict[str, object]:
    factory = cast(
        Callable[[Mapping[str, object], tuple[str, ...]], dict[str, object]],
        build_agent_feature_row,
    )
    return factory(gold_row, allowed_columns)


def test_target_injection_poison_fixture_raises_at_agent_input_boundary() -> None:
    assert "build_agent_feature_row" in features_package.__all__

    with _assert_raises(LeakageError, "forbidden columns"):
        _ = build_agent_feature_row(
            {
                "as_of_date": "2024-01-05",
                "kospi_close": 100.0,
                "target_next_day_return": 0.01,
            },
            allowed_columns=("as_of_date", "kospi_close"),
        )


def test_centered_window_poison_fixture_raises() -> None:
    with _assert_raises(LeakageError, "trailing"):
        assert_trailing_window(
            [1.0, 2.0, 3.0, 4.0, 5.0],
            current_index=3,
            window_size=3,
            window_bounds=(2, 4),
        )


def test_non_exact_trailing_window_bounds_raise_even_without_future_index() -> None:
    with _assert_raises(LeakageError, "exactly equal"):
        assert_trailing_window(
            [1.0, 2.0, 3.0, 4.0, 5.0],
            current_index=4,
            window_size=3,
            window_bounds=(1, 4),
        )


def test_full_period_normalization_poison_fixture_raises() -> None:
    with _assert_raises(LeakageError, "full-period"):
        assert_not_full_period_normalized(
            series_stats={"mean": 0.15, "std": 0.05},
            window_stats={"mean": 0.15, "std": 0.05},
        )


def test_future_join_walk_forward_poison_fixture_raises() -> None:
    with _assert_raises(LeakageError, "joined_as_of <= decision_date"):
        _ = _join_walk_forward_row(
            decision_date=date(2024, 1, 5),
            joined_as_of=date(2024, 1, 8),
            row={"kospi_close": 100.0},
        )


def test_future_join_walk_forward_accepts_safe_join_dates() -> None:
    row = _join_walk_forward_row(
        decision_date=date(2024, 1, 5),
        joined_as_of=date(2024, 1, 5),
        row={"kospi_close": 100.0},
    )

    assert row == {"kospi_close": 100.0}


def test_assert_no_forbidden_columns_accepts_safe_columns_and_custom_prefixes() -> None:
    assert_no_forbidden_columns(("as_of_date", "kospi_close"))

    with _assert_raises(LeakageError, "forbidden columns"):
        assert_no_forbidden_columns(
            ("label_internal",),
            forbidden_prefixes=("label_",),
        )


def test_assert_trailing_window_accepts_exact_trailing_bounds() -> None:
    assert_trailing_window(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        current_index=4,
        window_size=3,
        window_bounds=(2, 4),
    )


def test_assert_trailing_window_rejects_invalid_indices() -> None:
    for current_index, window_size, match in (
        (-1, 3, "existing observation"),
        (5, 3, "existing observation"),
        (2, 0, "window_size must be positive"),
        (1, 3, "sufficient history"),
    ):
        with _assert_raises(LeakageError, match):
            assert_trailing_window(
                [1.0, 2.0, 3.0, 4.0, 5.0],
                current_index=current_index,
                window_size=window_size,
            )


def test_assert_not_full_period_normalized_tolerates_distinct_window_stats() -> None:
    assert_not_full_period_normalized(
        series_stats={"mean": 0.15, "std": 0.05},
        window_stats={"mean": 0.16, "std": 0.05},
    )

    with _assert_raises(LeakageError, "missing statistic keys"):
        assert_not_full_period_normalized(
            series_stats={"mean": 0.15},
            window_stats={"mean": 0.15, "std": 0.05},
        )


def test_build_agent_feature_row_sanitizes_allowed_columns_only() -> None:
    row = build_agent_feature_row(
        {
            "as_of_date": "2024-01-05",
            "kospi_close": 100.0,
        },
        allowed_columns=("as_of_date", "kospi_close", "kospi_return_5d"),
    )

    assert row == {"as_of_date": "2024-01-05", "kospi_close": 100.0}


def test_build_agent_feature_row_rejects_non_whitelisted_columns() -> None:
    with _assert_raises(LeakageError, "non-whitelisted columns"):
        _ = build_agent_feature_row(
            {
                "as_of_date": "2024-01-05",
                "kospi_close": 100.0,
                "surprise_feature": 1.0,
            },
            allowed_columns=("as_of_date", "kospi_close"),
        )


def test_build_agent_feature_row_rejects_forbidden_allowed_columns() -> None:
    with _assert_raises(LeakageError, "forbidden columns"):
        _ = build_agent_feature_row(
            {"as_of_date": "2024-01-05", "kospi_close": 100.0},
            allowed_columns=("as_of_date", "future_hint"),
        )


def test_build_agent_feature_row_rejects_unsupported_scalar_values() -> None:
    for column, value in (
        ("is_holiday", True),
        ("published_at", date(2024, 1, 5)),
        ("turnover_krw", Decimal("10.5")),
    ):
        with _assert_raises(LeakageError, f"unsupported feature value for '{column}'"):
            _ = _build_untyped_agent_feature_row(
                {"as_of_date": "2024-01-05", column: value},
                allowed_columns=("as_of_date", column),
            )
