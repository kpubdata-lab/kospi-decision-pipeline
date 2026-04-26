from __future__ import annotations

from datetime import date
from typing import cast

import pytest

from kospi_decision_pipeline_core.schemas.backtest import (
    BacktestRow,
    FoldMetrics,
    OverallMetrics,
    backtest_row_from_mapping,
    backtest_row_to_mapping,
    fold_metrics_to_mapping,
    overall_metrics_to_mapping,
)


def test_backtest_row_serialization_round_trip() -> None:
    row = BacktestRow(
        fold_id=3,
        decision_date=date(2025, 2, 14),
        label="down",
        aggregate_score=-0.41,
        target_label="down",
        correct=True,
        snapshot_id="snapshot:2025-02-14",
        config_signature="cfg:123",
    )

    assert backtest_row_from_mapping(backtest_row_to_mapping(row)) == row


def test_metrics_mapping_helpers_emit_stable_shapes() -> None:
    fold = FoldMetrics(
        fold_id=2,
        fold_start=date(2025, 2, 3),
        fold_end=date(2025, 2, 7),
        decision_count=5,
        hit_rate=0.5,
        precision_up=None,
        precision_down=1.0,
        recall_up=0.25,
        recall_down=None,
        skip_rate=0.2,
        flat_rate=0.4,
    )
    overall = OverallMetrics(
        fold_count=1,
        period_start=date(2025, 2, 3),
        period_end=date(2025, 2, 14),
        decision_count=10,
        hit_rate=0.625,
        precision_up=0.75,
        precision_down=0.5,
        recall_up=0.6,
        recall_down=0.4,
        skip_rate=0.1,
        flat_rate=0.3,
        folds=(fold,),
    )

    assert fold_metrics_to_mapping(fold) == {
        "fold_id": 2,
        "fold_start": "2025-02-03",
        "fold_end": "2025-02-07",
        "decision_count": 5,
        "hit_rate": 0.5,
        "precision_up": None,
        "precision_down": 1.0,
        "recall_up": 0.25,
        "recall_down": None,
        "skip_rate": 0.2,
        "flat_rate": 0.4,
    }
    assert overall_metrics_to_mapping(overall) == {
        "fold_count": 1,
        "period_start": "2025-02-03",
        "period_end": "2025-02-14",
        "decision_count": 10,
        "hit_rate": 0.625,
        "precision_up": 0.75,
        "precision_down": 0.5,
        "recall_up": 0.6,
        "recall_down": 0.4,
        "skip_rate": 0.1,
        "flat_rate": 0.3,
        "folds": [
            {
                "fold_id": 2,
                "fold_start": "2025-02-03",
                "fold_end": "2025-02-07",
                "decision_count": 5,
                "hit_rate": 0.5,
                "precision_up": None,
                "precision_down": 1.0,
                "recall_up": 0.25,
                "recall_down": None,
                "skip_rate": 0.2,
                "flat_rate": 0.4,
            }
        ],
    }


def test_backtest_row_validates_runtime_values() -> None:
    with pytest.raises(ValueError, match="fold_id must be positive"):
        _ = BacktestRow(
            fold_id=0,
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=0.4,
            target_label="up",
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="snapshot_id must be a string"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=0.4,
            target_label="up",
            correct=True,
            snapshot_id=cast(str, cast(object, 1)),
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="aggregate_score must be a float"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=cast(float, cast(object, True)),
            target_label="up",
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="decision_date must be a date"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=cast(date, cast(object, "2025-02-14")),
            label="up",
            aggregate_score=0.4,
            target_label="up",
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="correct must be a bool"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=0.4,
            target_label="up",
            correct=cast(bool, cast(object, 1)),
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="fold_id must be an int"):
        _ = BacktestRow(
            fold_id=cast(int, cast(object, True)),
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=0.4,
            target_label="up",
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="label must be one of"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=date(2025, 2, 14),
            label=cast(str, cast(object, "flat")),
            aggregate_score=0.4,
            target_label="up",
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )

    with pytest.raises(ValueError, match="target_label must be one of"):
        _ = BacktestRow(
            fold_id=1,
            decision_date=date(2025, 2, 14),
            label="up",
            aggregate_score=0.4,
            target_label=cast(str, cast(object, "skip")),
            correct=True,
            snapshot_id="snapshot:2025-02-14",
            config_signature="cfg:123",
        )


def test_metrics_and_mapping_helpers_validate_error_branches() -> None:
    with pytest.raises(ValueError, match="fold_end must be on or after fold_start"):
        _ = FoldMetrics(
            fold_id=1,
            fold_start=date(2025, 2, 7),
            fold_end=date(2025, 2, 3),
            decision_count=1,
            hit_rate=0.0,
            precision_up=0.0,
            precision_down=0.0,
            recall_up=0.0,
            recall_down=0.0,
            skip_rate=0.0,
            flat_rate=0.0,
        )

    with pytest.raises(ValueError, match="period_end must be on or after period_start"):
        _ = OverallMetrics(
            fold_count=0,
            period_start=date(2025, 2, 7),
            period_end=date(2025, 2, 3),
            decision_count=0,
            hit_rate=None,
            precision_up=None,
            precision_down=None,
            recall_up=None,
            recall_down=None,
            skip_rate=None,
            flat_rate=None,
        )

    with pytest.raises(ValueError, match=r"fold_count must match len\(folds\)"):
        _ = OverallMetrics(
            fold_count=2,
            period_start=date(2025, 2, 3),
            period_end=date(2025, 2, 7),
            decision_count=1,
            hit_rate=0.0,
            precision_up=0.0,
            precision_down=0.0,
            recall_up=0.0,
            recall_down=0.0,
            skip_rate=0.0,
            flat_rate=0.0,
            folds=(
                FoldMetrics(
                    fold_id=1,
                    fold_start=date(2025, 2, 3),
                    fold_end=date(2025, 2, 3),
                    decision_count=1,
                    hit_rate=0.0,
                    precision_up=0.0,
                    precision_down=0.0,
                    recall_up=0.0,
                    recall_down=0.0,
                    skip_rate=0.0,
                    flat_rate=0.0,
                ),
            ),
        )

    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        _ = FoldMetrics(
            fold_id=1,
            fold_start=date(2025, 2, 3),
            fold_end=date(2025, 2, 3),
            decision_count=1,
            hit_rate=2.0,
            precision_up=0.0,
            precision_down=0.0,
            recall_up=0.0,
            recall_down=0.0,
            skip_rate=0.0,
            flat_rate=0.0,
        )

    with pytest.raises(ValueError, match="folds items must be FoldMetrics"):
        _ = OverallMetrics(
            fold_count=1,
            period_start=date(2025, 2, 3),
            period_end=date(2025, 2, 7),
            decision_count=1,
            hit_rate=0.0,
            precision_up=0.0,
            precision_down=0.0,
            recall_up=0.0,
            recall_down=0.0,
            skip_rate=0.0,
            flat_rate=0.0,
            folds=cast(tuple[FoldMetrics, ...], cast(object, (object(),))),
        )

    with pytest.raises(ValueError, match="decision_count must be non-negative"):
        _ = OverallMetrics(
            fold_count=0,
            period_start=date(2025, 2, 3),
            period_end=date(2025, 2, 7),
            decision_count=-1,
            hit_rate=None,
            precision_up=None,
            precision_down=None,
            recall_up=None,
            recall_down=None,
            skip_rate=None,
            flat_rate=None,
        )

    with pytest.raises(ValueError, match="decision_date must be an ISO date"):
        _ = backtest_row_from_mapping(
            {
                "fold_id": 1,
                "decision_date": "bad-date",
                "label": "up",
                "aggregate_score": 0.1,
                "target_label": "up",
                "correct": True,
                "snapshot_id": "snapshot:1",
                "config_signature": "cfg:1",
            }
        )

    with pytest.raises(ValueError, match="missing required key: snapshot_id"):
        _ = backtest_row_from_mapping(
            {
                "fold_id": 1,
                "decision_date": "2025-02-14",
                "label": "up",
                "aggregate_score": 0.1,
                "target_label": "up",
                "correct": True,
                "config_signature": "cfg:1",
            }
        )
