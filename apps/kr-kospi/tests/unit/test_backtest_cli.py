from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from kospi_decision_pipeline_core.schemas import DecisionResult


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_krx_close(snapshot_root: Path, trading_date: date, close: float) -> None:
    _write_parquet(
        snapshot_root / "krx" / "kospi_index" / f"{trading_date.isoformat()}.parquet",
        [
            {
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2025-02-10T09:00:00+00:00",
                "trade_date": trading_date,
                "close": close,
            }
        ],
    )


def _features_rows() -> list[dict[str, object]]:
    return [
        {"as_of_date": date(2025, 2, 3), "expected_decision": "up", "marker": 1},
        {"as_of_date": date(2025, 2, 4), "expected_decision": "skip", "marker": 2},
        {"as_of_date": date(2025, 2, 5), "expected_decision": "down", "marker": 3},
        {"as_of_date": date(2025, 2, 6), "expected_decision": "up", "marker": 4},
    ]


def _scenario_payload(
    agents_path: Path, features_path: Path, output_dir: Path
) -> dict[str, object]:
    return {
        "scenario_id": "kospi.next_day",
        "horizon": "next_day",
        "agents": ["technical", "domestic_macro", "flow", "valuation", "volatility", "decision"],
        "runtime": {
            "agents_config_path": str(agents_path),
            "features_path": str(features_path),
            "output_dir": str(output_dir),
        },
    }


def _decision_invoker_factory() -> object:
    def fake_scenario_invoker(
        scenario_path: Path | str,
        decision_date: date,
        features_path: Path | None,
        output_dir: Path | None,
    ) -> DecisionResult:
        assert output_dir is not None
        assert Path(scenario_path).is_file()
        assert features_path is not None
        rows = cast(list[dict[str, object]], pq.read_table(features_path).to_pylist())
        assert rows
        current_row = rows[-1]
        current_as_of_date = cast(date, current_row["as_of_date"])
        assert decision_date > current_as_of_date
        assert [cast(date, row["as_of_date"]) for row in rows] == [
            date(2025, 2, 3),
            date(2025, 2, 4),
            date(2025, 2, 5),
        ][: len(rows)]
        return DecisionResult(
            decision_date=decision_date,
            label=cast(str, current_row["expected_decision"]),
            aggregate_score=float(current_row["marker"]),
            threshold_up=0.25,
            threshold_down=-0.25,
            votes=(),
            config_signature="config-signature",
            snapshot_id=f"gold:{current_as_of_date.isoformat()}",
        )

    return fake_scenario_invoker


def test_backtest_command_writes_rows_and_summary_without_skip_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kospi_decision_pipeline_app_kr_kospi.cli import backtest_command

    features_path = tmp_path / "gold" / "decision_features.parquet"
    snapshot_root = tmp_path / "snapshot-root"
    output_dir = tmp_path / "backtest"
    scenario_path = tmp_path / "scenario.yaml"
    agents_path = tmp_path / "agents.yaml"
    _write_parquet(features_path, _features_rows())
    _write_krx_close(snapshot_root, date(2025, 2, 3), 100.0)
    _write_krx_close(snapshot_root, date(2025, 2, 4), 101.0)
    _write_krx_close(snapshot_root, date(2025, 2, 5), 101.0)
    _write_krx_close(snapshot_root, date(2025, 2, 6), 100.0)
    _write_yaml(
        agents_path, {"weights": {}, "thresholds": {"up": 0.25, "down": -0.25}, "agents": {}}
    )
    _write_yaml(scenario_path, _scenario_payload(agents_path, features_path, output_dir))
    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.backtest.runner.run_kospi_scenario",
        _decision_invoker_factory(),
    )

    assert (
        backtest_command(
            features=str(features_path),
            snapshot_root=str(snapshot_root),
            output_dir=str(output_dir),
            scenario=str(scenario_path),
            agents=str(agents_path),
        )
        == 0
    )

    rows_payload = [
        json.loads(line)
        for line in (output_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows_payload == [
        {
            "decision_date": "2025-02-03",
            "next_trading_date": "2025-02-04",
            "decision": "up",
            "truth_label": "up",
            "hit": True,
            "aggregate_score": 1.0,
            "snapshot_id": "gold:2025-02-03",
            "config_signature": "config-signature",
        },
        {
            "decision_date": "2025-02-04",
            "next_trading_date": "2025-02-05",
            "decision": "skip",
            "truth_label": "flat",
            "hit": None,
            "aggregate_score": 2.0,
            "snapshot_id": "gold:2025-02-04",
            "config_signature": "config-signature",
        },
        {
            "decision_date": "2025-02-05",
            "next_trading_date": "2025-02-06",
            "decision": "down",
            "truth_label": "down",
            "hit": True,
            "aggregate_score": 3.0,
            "snapshot_id": "gold:2025-02-05",
            "config_signature": "config-signature",
        },
    ]
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == {
        "evaluated_count": 3,
        "hit_count": 2,
        "skip_count": 1,
        "hit_rate": 1.0,
        "skip_rate": 1 / 3,
        "hit_rate_denominator": "evaluated_count - skip_count (skip excluded)",
    }


def test_backtest_command_is_identical_when_future_rows_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kospi_decision_pipeline_app_kr_kospi.cli import backtest_command

    full_features_path = tmp_path / "gold" / "decision_features.parquet"
    prefix_features_path = tmp_path / "gold" / "decision_features_prefix.parquet"
    snapshot_root = tmp_path / "snapshot-root"
    scenario_path = tmp_path / "scenario.yaml"
    agents_path = tmp_path / "agents.yaml"
    full_output_dir = tmp_path / "backtest-full"
    prefix_output_dir = tmp_path / "backtest-prefix"
    rows = _features_rows()
    _write_parquet(full_features_path, rows)
    _write_parquet(prefix_features_path, rows[:3])
    _write_krx_close(snapshot_root, date(2025, 2, 3), 100.0)
    _write_krx_close(snapshot_root, date(2025, 2, 4), 101.0)
    _write_krx_close(snapshot_root, date(2025, 2, 5), 101.0)
    _write_krx_close(snapshot_root, date(2025, 2, 6), 100.0)
    _write_yaml(
        agents_path, {"weights": {}, "thresholds": {"up": 0.25, "down": -0.25}, "agents": {}}
    )
    _write_yaml(scenario_path, _scenario_payload(agents_path, full_features_path, full_output_dir))
    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.backtest.runner.run_kospi_scenario",
        _decision_invoker_factory(),
    )

    assert (
        backtest_command(
            features=str(full_features_path),
            snapshot_root=str(snapshot_root),
            output_dir=str(full_output_dir),
            scenario=str(scenario_path),
            agents=str(agents_path),
        )
        == 0
    )
    assert (
        backtest_command(
            features=str(prefix_features_path),
            snapshot_root=str(snapshot_root),
            output_dir=str(prefix_output_dir),
            scenario=str(scenario_path),
            agents=str(agents_path),
        )
        == 0
    )

    assert (full_output_dir / "rows.jsonl").read_text(encoding="utf-8") == (
        prefix_output_dir / "rows.jsonl"
    ).read_text(encoding="utf-8")
