from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_core.backtest.runner import BacktestRunner
from kospi_decision_pipeline_core.backtest.walk_forward import WalkForwardSplitter
from kospi_decision_pipeline_core.schemas import DecisionResult
from kospi_decision_pipeline_core.schemas.backtest import BacktestRow


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...

    def slice(self, offset: int, length: int | None = None) -> _ArrowTable: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    if len(rows) == 0:
        return factory.from_pylist([{"trade_date": date(1970, 1, 1)}]).slice(0, 0)
    return factory.from_pylist(rows)


def _write_dataset(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def _dataset_rows() -> list[dict[str, object]]:
    trade_dates = [date(2025, 1, 6) + timedelta(days=offset) for offset in range(5)]
    labels = ["up", "flat", "down", "up", "down"]
    rows: list[dict[str, object]] = []
    for index, trade_date in enumerate(trade_dates):
        rows.append(
            {
                "trade_date": trade_date,
                "kospi_return_1d": float(index),
                "kospi_return_5d": float(index + 1),
                "target_next_day_simple_return": 0.01,
                "target_next_day_log_return": 0.01,
                "target_direction_label": labels[index],
            }
        )
    return rows


def test_backtest_runner_orchestrates_split_invoke_join_and_reports(tmp_path: Path) -> None:
    dataset_path = tmp_path / "data" / "gold" / "backtest_dataset.parquet"
    _write_dataset(dataset_path, _dataset_rows())
    scenario_path = tmp_path / "config" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text("scenario_id: test\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    calls: list[tuple[date, Path, Path | None]] = []

    def stub_invoker(
        scenario_path: Path | str,
        decision_date: date,
        features_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> DecisionResult:
        del scenario_path
        assert features_path is not None
        runtime_rows = pq.read_table(features_path).to_pylist()
        assert all("target_direction_label" not in row for row in runtime_rows)
        assert all("decision_date" in row for row in runtime_rows)
        calls.append((decision_date, features_path, output_dir))
        label_by_date = {
            date(2025, 1, 9): "down",
            date(2025, 1, 10): "skip",
            date(2025, 1, 13): "up",
        }
        score_by_date = {
            date(2025, 1, 9): -0.4,
            date(2025, 1, 10): 0.0,
            date(2025, 1, 13): 0.3,
        }
        return DecisionResult(
            decision_date=decision_date,
            label=label_by_date[decision_date],
            aggregate_score=score_by_date[decision_date],
            threshold_up=0.25,
            threshold_down=-0.25,
            votes=(),
            config_signature="cfg:test",
            snapshot_id=f"snapshot:{decision_date.isoformat()}",
        )

    runner = BacktestRunner(
        splitter=WalkForwardSplitter(min_train_rows=2, test_fold_size=2, gap_days=0),
        scenario_path=scenario_path,
        output_dir=output_dir,
        scenario_invoker=stub_invoker,
    )

    metrics = runner.run(dataset_path=dataset_path)

    assert [decision_date for decision_date, _, _ in calls] == [
        date(2025, 1, 9),
        date(2025, 1, 10),
        date(2025, 1, 13),
    ]
    assert all(path == calls[0][1] for _, path, _ in calls)
    assert metrics.fold_count == 2
    assert metrics.decision_count == 3
    assert metrics.hit_rate == 1 / 2
    assert metrics.precision_up == 0.0
    assert metrics.precision_down == 1.0
    assert metrics.recall_up == 0.0
    assert metrics.recall_down == 1 / 2
    assert metrics.skip_rate == 1 / 3
    assert metrics.flat_rate == 0.0
    assert [fold.fold_id for fold in metrics.folds] == [1, 2]

    rows_path = output_dir / "rows.jsonl"
    metrics_path = output_dir / "metrics.json"
    csv_path = output_dir / "metrics.csv"
    assert rows_path.is_file()
    assert metrics_path.is_file()
    assert csv_path.is_file()
    assert rows_path.read_text(encoding="utf-8").splitlines() == [
        '{"fold_id":1,"decision_date":"2025-01-09","label":"down","aggregate_score":-0.4,'
        '"target_label":"down","correct":true,"snapshot_id":"snapshot:2025-01-09",'
        '"config_signature":"cfg:test"}',
        '{"fold_id":1,"decision_date":"2025-01-10","label":"skip","aggregate_score":0.0,'
        '"target_label":"up","correct":false,"snapshot_id":"snapshot:2025-01-10",'
        '"config_signature":"cfg:test"}',
        '{"fold_id":2,"decision_date":"2025-01-13","label":"up","aggregate_score":0.3,'
        '"target_label":"down","correct":false,"snapshot_id":"snapshot:2025-01-13",'
        '"config_signature":"cfg:test"}',
    ]


def test_backtest_runner_is_byte_deterministic_across_repeated_runs(tmp_path: Path) -> None:
    dataset_path = tmp_path / "data" / "gold" / "backtest_dataset.parquet"
    _write_dataset(dataset_path, _dataset_rows())
    scenario_path = tmp_path / "config" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text("scenario_id: test\n", encoding="utf-8")

    def stub_invoker(
        scenario_path: Path | str,
        decision_date: date,
        features_path: Path | None = None,
        output_dir: Path | None = None,
    ) -> DecisionResult:
        del scenario_path, features_path, output_dir
        return DecisionResult(
            decision_date=decision_date,
            label="skip",
            aggregate_score=0.0,
            threshold_up=0.25,
            threshold_down=-0.25,
            votes=(),
            config_signature="cfg:test",
            snapshot_id=f"snapshot:{decision_date.isoformat()}",
        )

    first_output_dir = tmp_path / "first"
    second_output_dir = tmp_path / "second"
    for output_dir in (first_output_dir, second_output_dir):
        BacktestRunner(
            splitter=WalkForwardSplitter(min_train_rows=2, test_fold_size=2, gap_days=0),
            scenario_path=scenario_path,
            output_dir=output_dir,
            scenario_invoker=stub_invoker,
        ).run(dataset_path=dataset_path)

    assert (first_output_dir / "rows.jsonl").read_bytes() == (
        second_output_dir / "rows.jsonl"
    ).read_bytes()
    assert (first_output_dir / "metrics.json").read_bytes() == (
        second_output_dir / "metrics.json"
    ).read_bytes()


def test_backtest_runner_rows_are_sorted_by_fold_then_decision_date() -> None:
    rows = (
        BacktestRow(
            fold_id=2,
            decision_date=date(2025, 1, 13),
            label="skip",
            aggregate_score=0.0,
            target_label="down",
            correct=False,
            snapshot_id="snapshot:2",
            config_signature="cfg:test",
        ),
        BacktestRow(
            fold_id=1,
            decision_date=date(2025, 1, 10),
            label="skip",
            aggregate_score=0.0,
            target_label="up",
            correct=False,
            snapshot_id="snapshot:1b",
            config_signature="cfg:test",
        ),
        BacktestRow(
            fold_id=1,
            decision_date=date(2025, 1, 9),
            label="down",
            aggregate_score=-0.4,
            target_label="down",
            correct=True,
            snapshot_id="snapshot:1a",
            config_signature="cfg:test",
        ),
    )

    assert BacktestRunner._sorted_rows(rows) == (
        rows[2],
        rows[1],
        rows[0],
    )


def test_backtest_runner_validates_dataset_and_helper_inputs(tmp_path: Path) -> None:
    dataset_path = tmp_path / "data" / "gold" / "backtest_dataset.parquet"
    _write_dataset(
        dataset_path,
        [
            {
                "trade_date": date(2025, 1, 6),
                "kospi_return_1d": 0.0,
                "kospi_return_5d": 0.0,
                "target_next_day_simple_return": 0.0,
                "target_next_day_log_return": 0.0,
                "target_direction_label": "up",
            },
            {
                "trade_date": date(2025, 1, 6),
                "kospi_return_1d": 0.0,
                "kospi_return_5d": 0.0,
                "target_next_day_simple_return": 0.0,
                "target_next_day_log_return": 0.0,
                "target_direction_label": "down",
            },
        ],
    )
    runner = BacktestRunner(
        splitter=WalkForwardSplitter(min_train_rows=1, test_fold_size=1, gap_days=0),
        scenario_path=tmp_path / "scenario.yaml",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(ValueError, match="duplicate trade_date"):
        _ = runner._load_dataset_rows(dataset_path)

    invalid_dataset_path = tmp_path / "invalid.parquet"
    _write_dataset(
        invalid_dataset_path,
        [
            {
                "trade_date": "2025-01-06",
                "kospi_return_1d": 0.0,
                "kospi_return_5d": 0.0,
                "target_next_day_simple_return": 0.0,
                "target_next_day_log_return": 0.0,
                "target_direction_label": "up",
            }
        ],
    )
    with pytest.raises(ValueError, match="trade_date must be a date"):
        _ = runner._load_dataset_rows(invalid_dataset_path)


def test_backtest_runner_exercises_error_branches(tmp_path: Path) -> None:
    empty_dataset_path = tmp_path / "empty.parquet"
    _write_dataset(empty_dataset_path, [])
    scenario_path = tmp_path / "scenario.yaml"
    _ = scenario_path.write_text("scenario_id: test\n", encoding="utf-8")
    runner = BacktestRunner(
        splitter=WalkForwardSplitter(min_train_rows=10, test_fold_size=1, gap_days=0),
        scenario_path=scenario_path,
        output_dir=tmp_path / "out",
        scenario_invoker=lambda *_args, **_kwargs: cast(DecisionResult, object()),
    )

    with pytest.raises(ValueError, match="must not be empty"):
        _ = runner.run(dataset_path=empty_dataset_path)

    dataset_path = tmp_path / "dataset.parquet"
    _write_dataset(dataset_path, _dataset_rows())
    with pytest.raises(ValueError, match="produced no rows"):
        _ = runner.run(dataset_path=dataset_path)

    with pytest.raises(ValueError, match="strictly increasing"):
        _ = BacktestRunner._next_decision_date_for_test(
            (
                {"trade_date": date(2025, 1, 7)},
                {"trade_date": date(2025, 1, 7)},
            ),
            0,
        )

    with pytest.raises(ValueError, match="decision_date must be a date"):
        _ = BacktestRunner._require_decision_date_for_test({})

    with pytest.raises(ValueError, match="target_direction_label must be one of"):
        _ = BacktestRunner._require_target_label_for_test({"target_direction_label": "skip"})
