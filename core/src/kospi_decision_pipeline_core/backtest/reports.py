from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path

from kospi_decision_pipeline_core.schemas.backtest import (
    BacktestRow,
    FoldMetrics,
    OverallMetrics,
    backtest_row_to_mapping,
    fold_metrics_to_mapping,
    overall_metrics_to_mapping,
)


def write_backtest_jsonl(path: Path, rows: Sequence[object]) -> Path:
    sorted_rows = _normalize_backtest_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(_json_line(backtest_row_to_mapping(row)) for row in sorted_rows),
        encoding="utf-8",
    )
    return path


def write_metrics_json(path: Path, metrics: object) -> Path:
    normalized_metrics = _normalize_overall_metrics(metrics)
    payload = {
        "folds": [fold_metrics_to_mapping(fold) for fold in normalized_metrics.folds],
        "overall": {
            key: value
            for key, value in overall_metrics_to_mapping(normalized_metrics).items()
            if key != "folds"
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_metrics_csv(path: Path, metrics: object) -> Path:
    normalized_metrics = _normalize_overall_metrics(metrics)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_FIELDS)
        for fold in normalized_metrics.folds:
            writer.writerow(_csv_row_values(_fold_csv_row(fold)))
        writer.writerow(_csv_row_values(_overall_csv_row(normalized_metrics)))
    return path


_CSV_FIELDS = (
    "scope",
    "fold_id",
    "fold_start",
    "fold_end",
    "decision_count",
    "hit_rate",
    "precision_up",
    "precision_down",
    "recall_up",
    "recall_down",
    "skip_rate",
    "flat_rate",
)


def _json_line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"


def _fold_csv_row(metrics: FoldMetrics) -> dict[str, str]:
    return {
        "scope": "fold",
        "fold_id": str(metrics.fold_id),
        "fold_start": metrics.fold_start.isoformat(),
        "fold_end": metrics.fold_end.isoformat(),
        "decision_count": str(metrics.decision_count),
        "hit_rate": _stringify_optional_float(metrics.hit_rate),
        "precision_up": _stringify_optional_float(metrics.precision_up),
        "precision_down": _stringify_optional_float(metrics.precision_down),
        "recall_up": _stringify_optional_float(metrics.recall_up),
        "recall_down": _stringify_optional_float(metrics.recall_down),
        "skip_rate": _stringify_optional_float(metrics.skip_rate),
        "flat_rate": _stringify_optional_float(metrics.flat_rate),
    }


def _overall_csv_row(metrics: OverallMetrics) -> dict[str, str]:
    return {
        "scope": "overall",
        "fold_id": "",
        "fold_start": metrics.period_start.isoformat(),
        "fold_end": metrics.period_end.isoformat(),
        "decision_count": str(metrics.decision_count),
        "hit_rate": _stringify_optional_float(metrics.hit_rate),
        "precision_up": _stringify_optional_float(metrics.precision_up),
        "precision_down": _stringify_optional_float(metrics.precision_down),
        "recall_up": _stringify_optional_float(metrics.recall_up),
        "recall_down": _stringify_optional_float(metrics.recall_down),
        "skip_rate": _stringify_optional_float(metrics.skip_rate),
        "flat_rate": _stringify_optional_float(metrics.flat_rate),
    }


def _stringify_optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return str(value)


def _csv_row_values(row: dict[str, str]) -> list[str]:
    return [row[field] for field in _CSV_FIELDS]


def _normalize_backtest_rows(rows: Sequence[object]) -> tuple[BacktestRow, ...]:
    normalized_rows: list[BacktestRow] = []
    for row in rows:
        if not isinstance(row, BacktestRow):
            raise ValueError("rows must contain only BacktestRow values")
        normalized_rows.append(row)
    return tuple(sorted(normalized_rows, key=lambda row: (row.fold_id, row.decision_date)))


def _normalize_overall_metrics(metrics: object) -> OverallMetrics:
    if not isinstance(metrics, OverallMetrics):
        raise ValueError("metrics must be OverallMetrics")
    return metrics


__all__ = ["write_backtest_jsonl", "write_metrics_csv", "write_metrics_json"]
