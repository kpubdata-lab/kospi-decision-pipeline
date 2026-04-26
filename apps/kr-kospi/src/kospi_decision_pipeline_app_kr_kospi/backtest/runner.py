from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import log
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from kospi_decision_pipeline_core.calendar import TradingCalendar
from kospi_decision_pipeline_core.runtime.service import run_kospi_scenario
from kospi_decision_pipeline_core.schemas import DecisionResult, GroundTruthLabel, ModelLabel


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
class BacktestRow:
    decision_date: date
    next_trading_date: date
    decision: ModelLabel
    truth_label: GroundTruthLabel
    hit: bool | None
    aggregate_score: float
    snapshot_id: str
    config_signature: str

    def to_mapping(self) -> dict[str, object]:
        return {
            "decision_date": self.decision_date.isoformat(),
            "next_trading_date": self.next_trading_date.isoformat(),
            "decision": self.decision,
            "truth_label": self.truth_label,
            "hit": self.hit,
            "aggregate_score": self.aggregate_score,
            "snapshot_id": self.snapshot_id,
            "config_signature": self.config_signature,
        }


@dataclass(frozen=True, slots=True)
class BacktestSummary:
    evaluated_count: int
    hit_count: int
    skip_count: int
    hit_rate: float | None
    skip_rate: float | None
    hit_rate_denominator: str = "evaluated_count - skip_count (skip excluded)"

    def to_mapping(self) -> dict[str, object]:
        return {
            "evaluated_count": self.evaluated_count,
            "hit_count": self.hit_count,
            "skip_count": self.skip_count,
            "hit_rate": self.hit_rate,
            "skip_rate": self.skip_rate,
            "hit_rate_denominator": self.hit_rate_denominator,
        }


def run_backtest(
    *,
    features_path: Path,
    snapshot_root: Path,
    output_dir: Path,
    scenario_path: Path,
    agents_path: Path | None,
    scenario_invoker: Callable[[Path | str, date, Path | None, Path | None], DecisionResult]
    | None = None,
) -> BacktestSummary:
    feature_rows = _load_feature_rows(features_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_output_dir = output_dir / "decisions"
    scenario_override_path = _write_runtime_scenario_override(
        scenario_path=scenario_path,
        features_path=features_path,
        output_dir=runtime_output_dir,
        agents_path=agents_path,
    )
    backtest_rows: list[BacktestRow] = []
    calendar = TradingCalendar()
    resolved_scenario_invoker = run_kospi_scenario if scenario_invoker is None else scenario_invoker
    with TemporaryDirectory() as temporary_dir:
        temporary_root = Path(temporary_dir)
        for index, feature_row in enumerate(feature_rows):
            decision_date = _require_date(feature_row, "as_of_date")
            next_trading_date = calendar.next_trading_day(decision_date)
            truth_label = _truth_label(snapshot_root=snapshot_root, decision_date=decision_date)
            if truth_label is None:
                continue
            sliced_features_path = temporary_root / "runtime_features.parquet"
            _write_feature_slice(sliced_features_path, feature_rows[: index + 1])
            result = resolved_scenario_invoker(
                scenario_override_path,
                next_trading_date,
                sliced_features_path,
                runtime_output_dir,
            )
            backtest_rows.append(
                BacktestRow(
                    decision_date=decision_date,
                    next_trading_date=next_trading_date,
                    decision=result.label,
                    truth_label=truth_label,
                    hit=None if result.label == "skip" else result.label == truth_label,
                    aggregate_score=result.aggregate_score,
                    snapshot_id=result.snapshot_id,
                    config_signature=result.config_signature,
                )
            )
    if len(backtest_rows) == 0:
        raise ValueError("backtest produced no evaluable rows")
    summary = _summarize(backtest_rows)
    _ = (output_dir / "rows.jsonl").write_text(
        "".join(
            json.dumps(row.to_mapping(), ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in backtest_rows
        ),
        encoding="utf-8",
    )
    _ = (output_dir / "summary.json").write_text(
        json.dumps(summary.to_mapping(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _load_feature_rows(features_path: Path) -> tuple[dict[str, object], ...]:
    raw_rows = READ_TABLE(features_path).to_pylist()
    if len(raw_rows) == 0:
        raise ValueError("features parquet must not be empty")
    rows = tuple(
        sorted((dict(row) for row in raw_rows), key=lambda row: _require_date(row, "as_of_date"))
    )
    for index, row in enumerate(rows[1:], start=1):
        if _require_date(rows[index - 1], "as_of_date") == _require_date(row, "as_of_date"):
            raise ValueError("expected unique as_of_date values in gold features")
    return rows


def _write_runtime_scenario_override(
    *,
    scenario_path: Path,
    features_path: Path,
    output_dir: Path,
    agents_path: Path | None,
) -> Path:
    loaded = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ValueError("scenario payload must be a mapping")
    scenario_payload = dict(cast(Mapping[str, object], loaded))
    runtime = dict(_require_mapping(scenario_payload, "runtime"))
    runtime["features_path"] = str(features_path)
    runtime["output_dir"] = str(output_dir)
    if agents_path is not None:
        runtime["agents_config_path"] = str(agents_path)
    scenario_payload["runtime"] = runtime
    override_path = output_dir / "scenario.backtest.runtime.yaml"
    output_dir.mkdir(parents=True, exist_ok=True)
    _ = override_path.write_text(
        yaml.safe_dump(scenario_payload, sort_keys=False), encoding="utf-8"
    )
    return override_path


def _write_feature_slice(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    factory = cast(_ArrowTableFactory, pa.Table)
    table = factory.from_pylist([dict(row) for row in rows])
    WRITE_TABLE(table, path, compression="snappy")


def _truth_label(snapshot_root: Path, *, decision_date: date) -> GroundTruthLabel | None:
    calendar = TradingCalendar()
    next_trading_date = calendar.next_trading_day(decision_date)
    current_close = _load_krx_close(snapshot_root, decision_date)
    if current_close is None:
        raise ValueError(f"missing KRX close for {decision_date.isoformat()}")
    next_close = _load_krx_close(snapshot_root, next_trading_date)
    if next_close is None:
        return None
    if current_close <= 0.0 or next_close <= 0.0:
        raise ValueError("KRX closes must be positive")
    target_next_day_log_return = log(next_close / current_close)
    if target_next_day_log_return >= 0.001:
        return "up"
    if target_next_day_log_return <= -0.001:
        return "down"
    return "flat"


def _load_krx_close(snapshot_root: Path, trading_date: date) -> float | None:
    path = snapshot_root / "krx" / "kospi_index" / f"{trading_date.isoformat()}.parquet"
    if not path.is_file():
        return None
    rows = READ_TABLE(path).to_pylist()
    if len(rows) != 1:
        raise ValueError(f"expected exactly one KRX row for {trading_date.isoformat()}")
    return _require_float(rows[0], "close")


def _summarize(rows: Sequence[BacktestRow]) -> BacktestSummary:
    evaluated_count = len(rows)
    skip_count = sum(1 for row in rows if row.decision == "skip")
    hit_count = sum(1 for row in rows if row.hit is True)
    hit_denominator = evaluated_count - skip_count
    return BacktestSummary(
        evaluated_count=evaluated_count,
        hit_count=hit_count,
        skip_count=skip_count,
        hit_rate=None if hit_denominator == 0 else hit_count / hit_denominator,
        skip_rate=None if evaluated_count == 0 else skip_count / evaluated_count,
    )


def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be a mapping")
    return cast(Mapping[str, object], value)


def _require_date(row: Mapping[str, object], key: str) -> date:
    value = row.get(key)
    if not isinstance(value, date):
        raise ValueError(f"{key} must be a date")
    return value


def _require_float(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, int | float | Decimal | str)
    ):
        raise ValueError(f"{key} must be a numeric scalar")
    return float(value)


__all__ = ["BacktestRow", "BacktestSummary", "run_backtest"]
