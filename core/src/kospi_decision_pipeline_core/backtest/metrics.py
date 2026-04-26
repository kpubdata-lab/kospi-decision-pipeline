from __future__ import annotations

from collections.abc import Sequence

from kospi_decision_pipeline_core.schemas.backtest import BacktestRow, FoldMetrics, OverallMetrics


def compute_fold_metrics(rows: Sequence[BacktestRow]) -> FoldMetrics:
    normalized_rows = _normalize_rows(rows)
    fold_ids = {row.fold_id for row in normalized_rows}
    if len(fold_ids) != 1:
        raise ValueError("fold metrics require rows from exactly one fold")
    fold_id = normalized_rows[0].fold_id
    return FoldMetrics(
        fold_id=fold_id,
        fold_start=min(row.decision_date for row in normalized_rows),
        fold_end=max(row.decision_date for row in normalized_rows),
        decision_count=len(normalized_rows),
        hit_rate=_safe_ratio(_correct_count(normalized_rows), _non_skip_count(normalized_rows)),
        precision_up=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="up"),
            _predicted_count(normalized_rows, label="up"),
        ),
        precision_down=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="down"),
            _predicted_count(normalized_rows, label="down"),
        ),
        recall_up=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="up"),
            _target_count(normalized_rows, target_label="up"),
        ),
        recall_down=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="down"),
            _target_count(normalized_rows, target_label="down"),
        ),
        skip_rate=_safe_ratio(_label_count(normalized_rows, label="skip"), len(normalized_rows)),
        flat_rate=_safe_ratio(
            _target_count(normalized_rows, target_label="flat"), len(normalized_rows)
        ),
    )


def compute_overall_metrics(rows: Sequence[BacktestRow]) -> OverallMetrics:
    normalized_rows = _normalize_rows(rows)
    return OverallMetrics(
        fold_count=len({row.fold_id for row in normalized_rows}),
        period_start=min(row.decision_date for row in normalized_rows),
        period_end=max(row.decision_date for row in normalized_rows),
        decision_count=len(normalized_rows),
        hit_rate=_safe_ratio(_correct_count(normalized_rows), _non_skip_count(normalized_rows)),
        precision_up=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="up"),
            _predicted_count(normalized_rows, label="up"),
        ),
        precision_down=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="down"),
            _predicted_count(normalized_rows, label="down"),
        ),
        recall_up=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="up"),
            _target_count(normalized_rows, target_label="up"),
        ),
        recall_down=_safe_ratio(
            _predicted_target_matches(normalized_rows, label="down"),
            _target_count(normalized_rows, target_label="down"),
        ),
        skip_rate=_safe_ratio(_label_count(normalized_rows, label="skip"), len(normalized_rows)),
        flat_rate=_safe_ratio(
            _target_count(normalized_rows, target_label="flat"), len(normalized_rows)
        ),
    )


def _normalize_rows(rows: Sequence[BacktestRow]) -> tuple[BacktestRow, ...]:
    if len(rows) == 0:
        raise ValueError("rows must not be empty")
    return tuple(rows)


def _correct_count(rows: Sequence[BacktestRow]) -> int:
    return sum(1 for row in rows if row.correct)


def _non_skip_count(rows: Sequence[BacktestRow]) -> int:
    return sum(1 for row in rows if row.label != "skip")


def _predicted_target_matches(rows: Sequence[BacktestRow], *, label: str) -> int:
    return sum(1 for row in rows if row.label == label and row.target_label == label)


def _predicted_count(rows: Sequence[BacktestRow], *, label: str) -> int:
    return sum(1 for row in rows if row.label == label)


def _target_count(rows: Sequence[BacktestRow], *, target_label: str) -> int:
    return sum(1 for row in rows if row.target_label == target_label)


def _label_count(rows: Sequence[BacktestRow], *, label: str) -> int:
    return sum(1 for row in rows if row.label == label)


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


__all__ = ["compute_fold_metrics", "compute_overall_metrics"]
