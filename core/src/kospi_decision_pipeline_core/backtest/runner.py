from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq

from kospi_decision_pipeline_core.runtime.service import run_kospi_scenario
from kospi_decision_pipeline_core.schemas import DecisionResult
from kospi_decision_pipeline_core.schemas.backtest import BacktestRow, OverallMetrics
from kospi_decision_pipeline_core.schemas.decisions import GroundTruthLabel

from .metrics import compute_fold_metrics, compute_overall_metrics
from .reports import write_backtest_jsonl, write_metrics_csv, write_metrics_json
from .walk_forward import WalkForwardSplitter


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


@dataclass(frozen=True, slots=True)
class BacktestRunner:
    splitter: WalkForwardSplitter
    scenario_path: Path
    output_dir: Path
    scenario_invoker: Callable[
        [Path | str, date, Path | None, Path | None],
        DecisionResult,
    ] = run_kospi_scenario

    def run(self, *, dataset_path: Path) -> OverallMetrics:
        dataset_rows = self._load_dataset_rows(dataset_path)
        runtime_rows = self._build_runtime_rows(dataset_rows)
        sorted_trade_dates = tuple(
            _require_trade_date(row, context="trade_date") for row in runtime_rows
        )
        fold_rows: list[BacktestRow] = []

        with TemporaryDirectory() as temporary_dir:
            runtime_features_path = Path(temporary_dir) / "runtime_features.parquet"
            scenario_output_dir = Path(temporary_dir) / "scenario-output"
            self._write_runtime_features(runtime_features_path, runtime_rows)
            for fold in self.splitter.split(sorted_trade_dates):
                for test_index in fold.test_indices:
                    runtime_row = runtime_rows[test_index]
                    decision_date = _require_decision_date(runtime_row)
                    target_label = _require_target_label(runtime_row)
                    result = self.scenario_invoker(
                        self.scenario_path,
                        decision_date,
                        runtime_features_path,
                        scenario_output_dir,
                    )
                    fold_rows.append(
                        BacktestRow(
                            fold_id=fold.fold_id,
                            decision_date=result.decision_date,
                            label=result.label,
                            aggregate_score=result.aggregate_score,
                            target_label=target_label,
                            correct=result.label == target_label,
                            snapshot_id=result.snapshot_id,
                            config_signature=result.config_signature,
                        )
                    )

        sorted_rows = self._sorted_rows(fold_rows)
        if len(sorted_rows) == 0:
            raise ValueError("backtest runner produced no rows")
        folds = tuple(
            compute_fold_metrics(tuple(row for row in sorted_rows if row.fold_id == fold_id))
            for fold_id in sorted({row.fold_id for row in sorted_rows})
        )
        overall_metrics = replace(compute_overall_metrics(sorted_rows), folds=folds)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        _ = write_backtest_jsonl(self.output_dir / "rows.jsonl", sorted_rows)
        _ = write_metrics_json(self.output_dir / "metrics.json", overall_metrics)
        _ = write_metrics_csv(self.output_dir / "metrics.csv", overall_metrics)
        return overall_metrics

    @staticmethod
    def _sorted_rows(rows: Sequence[BacktestRow]) -> tuple[BacktestRow, ...]:
        return tuple(sorted(rows, key=lambda row: (row.fold_id, row.decision_date)))

    @staticmethod
    def _next_decision_date_for_test(rows: Sequence[Mapping[str, object]], index: int) -> date:
        return _next_decision_date(rows, index)

    @staticmethod
    def _require_decision_date_for_test(row: Mapping[str, object]) -> date:
        return _require_decision_date(row)

    @staticmethod
    def _require_target_label_for_test(row: Mapping[str, object]) -> GroundTruthLabel:
        return _require_target_label(row)

    def _load_dataset_rows(self, dataset_path: Path) -> tuple[dict[str, object], ...]:
        raw_rows = READ_TABLE(dataset_path).to_pylist()
        if len(raw_rows) == 0:
            raise ValueError("backtest dataset must not be empty")
        sorted_rows = tuple(sorted((dict(row) for row in raw_rows), key=_trade_date_sort_key))
        for index, row in enumerate(sorted_rows):
            _ = _require_trade_date(row, context="trade_date")
            _ = _require_target_label(row)
            if index > 0 and sorted_rows[index - 1]["trade_date"] == row["trade_date"]:
                raise ValueError("duplicate trade_date in backtest dataset")
        return sorted_rows

    def _build_runtime_rows(
        self,
        dataset_rows: Sequence[Mapping[str, object]],
    ) -> tuple[dict[str, object], ...]:
        runtime_rows: list[dict[str, object]] = []
        for index, row in enumerate(dataset_rows):
            trade_date = _require_trade_date(row, context="trade_date")
            decision_date = _next_decision_date(dataset_rows, index)
            runtime_row = {
                key: value
                for key, value in row.items()
                if not key.startswith("target_") and not key.startswith("future_")
            }
            runtime_row["decision_date"] = decision_date
            runtime_row["target_direction_label"] = _require_target_label(row)
            runtime_row["trade_date"] = trade_date
            runtime_rows.append(runtime_row)
        return tuple(runtime_rows)

    def _write_runtime_features(
        self,
        path: Path,
        runtime_rows: Sequence[Mapping[str, object]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        factory = cast(_ArrowTableFactory, pa.Table)
        table = factory.from_pylist(
            [
                {key: value for key, value in row.items() if key != "target_direction_label"}
                for row in runtime_rows
            ]
        )
        WRITE_TABLE(table, path, compression="snappy")


def _trade_date_sort_key(row: Mapping[str, object]) -> date:
    return _require_trade_date(row, context="trade_date")


def _next_decision_date(rows: Sequence[Mapping[str, object]], index: int) -> date:
    current_trade_date = _require_trade_date(rows[index], context="trade_date")
    if index + 1 < len(rows):
        next_trade_date = _require_trade_date(rows[index + 1], context="trade_date")
        if next_trade_date <= current_trade_date:
            raise ValueError("backtest dataset trade_date must be strictly increasing")
        return next_trade_date
    return _next_weekday(current_trade_date)


def _next_weekday(current_trade_date: date) -> date:
    candidate = current_trade_date + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _require_trade_date(row: Mapping[str, object], *, context: str) -> date:
    value = row.get(context)
    if not isinstance(value, date):
        raise ValueError(f"{context} must be a date")
    return value


def _require_decision_date(row: Mapping[str, object]) -> date:
    value = row.get("decision_date")
    if not isinstance(value, date):
        raise ValueError("decision_date must be a date")
    return value


def _require_target_label(row: Mapping[str, object]) -> GroundTruthLabel:
    value = row.get("target_direction_label")
    if value not in {"up", "down", "flat"}:
        raise ValueError("target_direction_label must be one of: down, flat, up")
    return cast(GroundTruthLabel, value)


__all__ = ["BacktestRunner"]
