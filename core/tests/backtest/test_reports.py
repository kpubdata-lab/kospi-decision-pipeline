from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from kospi_decision_pipeline_core.backtest.reports import (
    write_backtest_jsonl,
    write_metrics_csv,
    write_metrics_json,
)
from kospi_decision_pipeline_core.schemas.backtest import BacktestRow, FoldMetrics, OverallMetrics
import pytest


def _row(*, fold_id: int, decision_date: date, label: str, target_label: str) -> BacktestRow:
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


def test_write_backtest_jsonl_sorts_rows_deterministically(tmp_path: Path) -> None:
    output_path = tmp_path / "rows.jsonl"

    rows = (
        _row(fold_id=2, decision_date=date(2025, 1, 8), label="down", target_label="down"),
        _row(fold_id=1, decision_date=date(2025, 1, 7), label="up", target_label="up"),
        _row(fold_id=1, decision_date=date(2025, 1, 6), label="skip", target_label="flat"),
    )

    write_backtest_jsonl(output_path, rows)
    first_bytes = output_path.read_bytes()
    write_backtest_jsonl(output_path, rows)

    assert output_path.read_bytes() == first_bytes
    assert output_path.read_text(encoding="utf-8") == (
        '{"fold_id":1,"decision_date":"2025-01-06","label":"skip","aggregate_score":0.0,'
        '"target_label":"flat","correct":false,"snapshot_id":"snapshot:2025-01-06",'
        '"config_signature":"cfg:test"}\n'
        '{"fold_id":1,"decision_date":"2025-01-07","label":"up","aggregate_score":0.0,'
        '"target_label":"up","correct":true,"snapshot_id":"snapshot:2025-01-07",'
        '"config_signature":"cfg:test"}\n'
        '{"fold_id":2,"decision_date":"2025-01-08","label":"down","aggregate_score":0.0,'
        '"target_label":"down","correct":true,"snapshot_id":"snapshot:2025-01-08",'
        '"config_signature":"cfg:test"}\n'
    )


def test_write_metrics_json_emits_stable_summary_shape(tmp_path: Path) -> None:
    output_path = tmp_path / "metrics.json"
    metrics = OverallMetrics(
        fold_count=1,
        period_start=date(2025, 1, 6),
        period_end=date(2025, 1, 8),
        decision_count=3,
        hit_rate=1.0,
        precision_up=1.0,
        precision_down=None,
        recall_up=1.0,
        recall_down=None,
        skip_rate=1 / 3,
        flat_rate=1 / 3,
        folds=(
            FoldMetrics(
                fold_id=1,
                fold_start=date(2025, 1, 6),
                fold_end=date(2025, 1, 8),
                decision_count=3,
                hit_rate=1.0,
                precision_up=1.0,
                precision_down=None,
                recall_up=1.0,
                recall_down=None,
                skip_rate=1 / 3,
                flat_rate=1 / 3,
            ),
        ),
    )

    write_metrics_json(output_path, metrics)
    first_bytes = output_path.read_bytes()
    write_metrics_json(output_path, metrics)

    assert output_path.read_bytes() == first_bytes
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "folds": [
            {
                "fold_id": 1,
                "fold_start": "2025-01-06",
                "fold_end": "2025-01-08",
                "decision_count": 3,
                "hit_rate": 1.0,
                "precision_up": 1.0,
                "precision_down": None,
                "recall_up": 1.0,
                "recall_down": None,
                "skip_rate": 1 / 3,
                "flat_rate": 1 / 3,
            }
        ],
        "overall": {
            "fold_count": 1,
            "period_start": "2025-01-06",
            "period_end": "2025-01-08",
            "decision_count": 3,
            "hit_rate": 1.0,
            "precision_up": 1.0,
            "precision_down": None,
            "recall_up": 1.0,
            "recall_down": None,
            "skip_rate": 1 / 3,
            "flat_rate": 1 / 3,
        },
    }


def test_write_metrics_csv_emits_human_readable_rows(tmp_path: Path) -> None:
    output_path = tmp_path / "metrics.csv"
    metrics = OverallMetrics(
        fold_count=2,
        period_start=date(2025, 1, 6),
        period_end=date(2025, 1, 10),
        decision_count=5,
        hit_rate=0.5,
        precision_up=1.0,
        precision_down=0.0,
        recall_up=0.5,
        recall_down=0.0,
        skip_rate=0.2,
        flat_rate=0.2,
        folds=(
            FoldMetrics(
                fold_id=1,
                fold_start=date(2025, 1, 6),
                fold_end=date(2025, 1, 7),
                decision_count=2,
                hit_rate=1.0,
                precision_up=1.0,
                precision_down=None,
                recall_up=1.0,
                recall_down=1.0,
                skip_rate=0.0,
                flat_rate=0.0,
            ),
            FoldMetrics(
                fold_id=2,
                fold_start=date(2025, 1, 8),
                fold_end=date(2025, 1, 10),
                decision_count=3,
                hit_rate=0.0,
                precision_up=None,
                precision_down=0.0,
                recall_up=0.0,
                recall_down=0.0,
                skip_rate=1 / 3,
                flat_rate=1 / 3,
            ),
        ),
    )

    write_metrics_csv(output_path, metrics)

    assert output_path.read_text(encoding="utf-8") == (
        "scope,fold_id,fold_start,fold_end,decision_count,hit_rate,precision_up,precision_down,recall_up,recall_down,skip_rate,flat_rate\n"
        "fold,1,2025-01-06,2025-01-07,2,1.0,1.0,,1.0,1.0,0.0,0.0\n"
        "fold,2,2025-01-08,2025-01-10,3,0.0,,0.0,0.0,0.0,0.3333333333333333,0.3333333333333333\n"
        "overall,,2025-01-06,2025-01-10,5,0.5,1.0,0.0,0.5,0.0,0.2,0.2\n"
    )


def test_report_writers_validate_input_types(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="BacktestRow"):
        _ = write_backtest_jsonl(tmp_path / "rows.jsonl", (object(),))

    with pytest.raises(ValueError, match="OverallMetrics"):
        _ = write_metrics_json(tmp_path / "metrics.json", object())

    with pytest.raises(ValueError, match="OverallMetrics"):
        _ = write_metrics_csv(tmp_path / "metrics.csv", object())
