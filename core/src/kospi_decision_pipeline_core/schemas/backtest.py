from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

from .decisions import GroundTruthLabel, ModelLabel


@dataclass(frozen=True, slots=True)
class BacktestRow:
    fold_id: int
    decision_date: date
    label: ModelLabel
    aggregate_score: float
    target_label: GroundTruthLabel
    correct: bool
    snapshot_id: str
    config_signature: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _ensure_positive_int(self.fold_id, context="fold_id"))
        object.__setattr__(
            self,
            "decision_date",
            _ensure_date(self.decision_date, context="decision_date"),
        )
        object.__setattr__(self, "label", _ensure_model_label(self.label, context="label"))
        object.__setattr__(
            self,
            "aggregate_score",
            _ensure_float(self.aggregate_score, context="aggregate_score"),
        )
        object.__setattr__(
            self,
            "target_label",
            _ensure_ground_truth_label(self.target_label, context="target_label"),
        )
        object.__setattr__(self, "correct", _ensure_bool(self.correct, context="correct"))
        object.__setattr__(
            self,
            "snapshot_id",
            _ensure_string(self.snapshot_id, context="snapshot_id"),
        )
        object.__setattr__(
            self,
            "config_signature",
            _ensure_string(self.config_signature, context="config_signature"),
        )


@dataclass(frozen=True, slots=True)
class FoldMetrics:
    fold_id: int
    fold_start: date
    fold_end: date
    decision_count: int
    hit_rate: float | None
    precision_up: float | None
    precision_down: float | None
    recall_up: float | None
    recall_down: float | None
    skip_rate: float | None
    flat_rate: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fold_id", _ensure_positive_int(self.fold_id, context="fold_id"))
        object.__setattr__(self, "fold_start", _ensure_date(self.fold_start, context="fold_start"))
        object.__setattr__(self, "fold_end", _ensure_date(self.fold_end, context="fold_end"))
        object.__setattr__(
            self,
            "decision_count",
            _ensure_non_negative_int(self.decision_count, context="decision_count"),
        )
        if self.fold_end < self.fold_start:
            raise ValueError("fold_end must be on or after fold_start")
        _validate_optional_rate(self.hit_rate, context="hit_rate")
        _validate_optional_rate(self.precision_up, context="precision_up")
        _validate_optional_rate(self.precision_down, context="precision_down")
        _validate_optional_rate(self.recall_up, context="recall_up")
        _validate_optional_rate(self.recall_down, context="recall_down")
        _validate_optional_rate(self.skip_rate, context="skip_rate")
        _validate_optional_rate(self.flat_rate, context="flat_rate")


@dataclass(frozen=True, slots=True)
class OverallMetrics:
    fold_count: int
    period_start: date
    period_end: date
    decision_count: int
    hit_rate: float | None
    precision_up: float | None
    precision_down: float | None
    recall_up: float | None
    recall_down: float | None
    skip_rate: float | None
    flat_rate: float | None
    folds: tuple[FoldMetrics, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fold_count",
            _ensure_non_negative_int(self.fold_count, context="fold_count"),
        )
        object.__setattr__(
            self,
            "period_start",
            _ensure_date(self.period_start, context="period_start"),
        )
        object.__setattr__(self, "period_end", _ensure_date(self.period_end, context="period_end"))
        object.__setattr__(
            self,
            "decision_count",
            _ensure_non_negative_int(self.decision_count, context="decision_count"),
        )
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if self.fold_count != len(self.folds) and len(self.folds) != 0:
            raise ValueError("fold_count must match len(folds)")
        _validate_optional_rate(self.hit_rate, context="hit_rate")
        _validate_optional_rate(self.precision_up, context="precision_up")
        _validate_optional_rate(self.precision_down, context="precision_down")
        _validate_optional_rate(self.recall_up, context="recall_up")
        _validate_optional_rate(self.recall_down, context="recall_down")
        _validate_optional_rate(self.skip_rate, context="skip_rate")
        _validate_optional_rate(self.flat_rate, context="flat_rate")
        for fold in self.folds:
            if type(fold) is not FoldMetrics:
                raise ValueError("folds items must be FoldMetrics")


def backtest_row_to_mapping(row: BacktestRow) -> dict[str, object]:
    return {
        "fold_id": row.fold_id,
        "decision_date": row.decision_date.isoformat(),
        "label": row.label,
        "aggregate_score": row.aggregate_score,
        "target_label": row.target_label,
        "correct": row.correct,
        "snapshot_id": row.snapshot_id,
        "config_signature": row.config_signature,
    }


def backtest_row_from_mapping(mapping: Mapping[str, object]) -> BacktestRow:
    return BacktestRow(
        fold_id=_require_int(mapping, "fold_id"),
        decision_date=_require_date_string(mapping, "decision_date"),
        label=_require_model_label(mapping, "label"),
        aggregate_score=_require_float(mapping, "aggregate_score"),
        target_label=_require_ground_truth_label(mapping, "target_label"),
        correct=_require_bool(mapping, "correct"),
        snapshot_id=_require_string(mapping, "snapshot_id"),
        config_signature=_require_string(mapping, "config_signature"),
    )


def fold_metrics_to_mapping(metrics: FoldMetrics) -> dict[str, object]:
    return {
        "fold_id": metrics.fold_id,
        "fold_start": metrics.fold_start.isoformat(),
        "fold_end": metrics.fold_end.isoformat(),
        "decision_count": metrics.decision_count,
        "hit_rate": metrics.hit_rate,
        "precision_up": metrics.precision_up,
        "precision_down": metrics.precision_down,
        "recall_up": metrics.recall_up,
        "recall_down": metrics.recall_down,
        "skip_rate": metrics.skip_rate,
        "flat_rate": metrics.flat_rate,
    }


def overall_metrics_to_mapping(metrics: OverallMetrics) -> dict[str, object]:
    return {
        "fold_count": metrics.fold_count,
        "period_start": metrics.period_start.isoformat(),
        "period_end": metrics.period_end.isoformat(),
        "decision_count": metrics.decision_count,
        "hit_rate": metrics.hit_rate,
        "precision_up": metrics.precision_up,
        "precision_down": metrics.precision_down,
        "recall_up": metrics.recall_up,
        "recall_down": metrics.recall_down,
        "skip_rate": metrics.skip_rate,
        "flat_rate": metrics.flat_rate,
        "folds": [fold_metrics_to_mapping(fold) for fold in metrics.folds],
    }


def _ensure_string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _ensure_float(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} must be a float")
    return float(value)


def _ensure_date(value: object, *, context: str) -> date:
    if not isinstance(value, date):
        raise ValueError(f"{context} must be a date")
    return value


def _ensure_bool(value: object, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a bool")
    return value


def _ensure_positive_int(value: object, *, context: str) -> int:
    normalized = _ensure_non_negative_int(value, context=context)
    if normalized <= 0:
        raise ValueError(f"{context} must be positive")
    return normalized


def _ensure_non_negative_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an int")
    if value < 0:
        raise ValueError(f"{context} must be non-negative")
    return value


def _ensure_model_label(value: object, *, context: str) -> ModelLabel:
    if not isinstance(value, str) or value not in {"up", "down", "skip"}:
        raise ValueError(f"{context} must be one of: down, skip, up")
    return cast(ModelLabel, value)


def _ensure_ground_truth_label(value: object, *, context: str) -> GroundTruthLabel:
    if not isinstance(value, str) or value not in {"up", "down", "flat"}:
        raise ValueError(f"{context} must be one of: down, flat, up")
    return cast(GroundTruthLabel, value)


def _validate_optional_rate(value: float | None, *, context: str) -> None:
    if value is None:
        return
    normalized = _ensure_float(value, context=context)
    if normalized < 0.0 or normalized > 1.0:
        raise ValueError(f"{context} must be between 0.0 and 1.0")


def _require_value(mapping: Mapping[str, object], key: str) -> object:
    if key not in mapping:
        raise ValueError(f"missing required key: {key}")
    return mapping[key]


def _require_int(mapping: Mapping[str, object], key: str) -> int:
    return _ensure_non_negative_int(_require_value(mapping, key), context=key)


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    return _ensure_string(_require_value(mapping, key), context=key)


def _require_bool(mapping: Mapping[str, object], key: str) -> bool:
    return _ensure_bool(_require_value(mapping, key), context=key)


def _require_float(mapping: Mapping[str, object], key: str) -> float:
    return _ensure_float(_require_value(mapping, key), context=key)


def _require_date_string(mapping: Mapping[str, object], key: str) -> date:
    value = _require_string(mapping, key)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date") from exc


def _require_model_label(mapping: Mapping[str, object], key: str) -> ModelLabel:
    return _ensure_model_label(_require_value(mapping, key), context=key)


def _require_ground_truth_label(mapping: Mapping[str, object], key: str) -> GroundTruthLabel:
    return _ensure_ground_truth_label(_require_value(mapping, key), context=key)


__all__ = [
    "BacktestRow",
    "FoldMetrics",
    "OverallMetrics",
    "backtest_row_from_mapping",
    "backtest_row_to_mapping",
    "fold_metrics_to_mapping",
    "overall_metrics_to_mapping",
]
