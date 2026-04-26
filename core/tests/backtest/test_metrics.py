from __future__ import annotations

from datetime import date

from kospi_decision_pipeline_core.backtest.metrics import (
    compute_fold_metrics,
    compute_overall_metrics,
)
from kospi_decision_pipeline_core.schemas.backtest import BacktestRow
import pytest


def _row(
    *,
    fold_id: int,
    decision_date: date,
    label: str,
    target_label: str,
) -> BacktestRow:
    return BacktestRow(
        fold_id=fold_id,
        decision_date=decision_date,
        label=label,
        aggregate_score=0.0,
        target_label=target_label,
        correct=label == target_label and label != "skip",
        snapshot_id=f"snapshot:{decision_date.isoformat()}",
        config_signature="cfg:test",
    )


def test_compute_fold_metrics_covers_all_label_target_pairs() -> None:
    rows = (
        _row(fold_id=1, decision_date=date(2025, 1, 2), label="up", target_label="up"),
        _row(fold_id=1, decision_date=date(2025, 1, 3), label="up", target_label="down"),
        _row(fold_id=1, decision_date=date(2025, 1, 6), label="up", target_label="flat"),
        _row(fold_id=1, decision_date=date(2025, 1, 7), label="down", target_label="up"),
        _row(fold_id=1, decision_date=date(2025, 1, 8), label="down", target_label="down"),
        _row(fold_id=1, decision_date=date(2025, 1, 9), label="down", target_label="flat"),
        _row(fold_id=1, decision_date=date(2025, 1, 10), label="skip", target_label="up"),
        _row(fold_id=1, decision_date=date(2025, 1, 13), label="skip", target_label="down"),
        _row(fold_id=1, decision_date=date(2025, 1, 14), label="skip", target_label="flat"),
    )

    metrics = compute_fold_metrics(rows)

    assert metrics.fold_id == 1
    assert metrics.fold_start == date(2025, 1, 2)
    assert metrics.fold_end == date(2025, 1, 14)
    assert metrics.decision_count == 9
    assert metrics.hit_rate == 2 / 6
    assert metrics.precision_up == 1 / 3
    assert metrics.precision_down == 1 / 3
    assert metrics.recall_up == 1 / 3
    assert metrics.recall_down == 1 / 3
    assert metrics.skip_rate == 3 / 9
    assert metrics.flat_rate == 3 / 9


def test_compute_fold_metrics_returns_none_for_zero_denominator_cases() -> None:
    rows = (
        _row(fold_id=2, decision_date=date(2025, 2, 3), label="skip", target_label="flat"),
        _row(fold_id=2, decision_date=date(2025, 2, 4), label="skip", target_label="flat"),
    )

    metrics = compute_fold_metrics(rows)

    assert metrics.hit_rate is None
    assert metrics.precision_up is None
    assert metrics.precision_down is None
    assert metrics.recall_up is None
    assert metrics.recall_down is None
    assert metrics.skip_rate == 1.0
    assert metrics.flat_rate == 1.0


def test_compute_overall_metrics_aggregates_across_folds() -> None:
    rows = (
        _row(fold_id=1, decision_date=date(2025, 1, 2), label="up", target_label="up"),
        _row(fold_id=1, decision_date=date(2025, 1, 3), label="skip", target_label="down"),
        _row(fold_id=2, decision_date=date(2025, 1, 6), label="down", target_label="down"),
        _row(fold_id=2, decision_date=date(2025, 1, 7), label="down", target_label="flat"),
    )

    metrics = compute_overall_metrics(rows)

    assert metrics.fold_count == 2
    assert metrics.decision_count == 4
    assert metrics.period_start == date(2025, 1, 2)
    assert metrics.period_end == date(2025, 1, 7)
    assert metrics.hit_rate == 2 / 3
    assert metrics.precision_up == 1.0
    assert metrics.precision_down == 1 / 2
    assert metrics.recall_up == 1.0
    assert metrics.recall_down == 1 / 2
    assert metrics.skip_rate == 1 / 4
    assert metrics.flat_rate == 1 / 4


def test_metrics_reject_empty_rows_and_mixed_fold_rows() -> None:
    with pytest.raises(ValueError, match="rows must not be empty"):
        _ = compute_overall_metrics(())

    with pytest.raises(ValueError, match="exactly one fold"):
        _ = compute_fold_metrics(
            (
                _row(fold_id=1, decision_date=date(2025, 1, 2), label="up", target_label="up"),
                _row(
                    fold_id=2,
                    decision_date=date(2025, 1, 3),
                    label="down",
                    target_label="down",
                ),
            )
        )
