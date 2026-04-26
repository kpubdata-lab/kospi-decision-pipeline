from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from kospi_decision_pipeline_core.schemas import DecisionResult, ModelLabel


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


class _ScenarioInvoker(Protocol):
    def __call__(
        self,
        scenario_path: Path | str,
        decision_date: date,
        features_path: Path | None,
        output_dir: Path | None,
    ) -> DecisionResult: ...


class _LoadFeatureRows(Protocol):
    def __call__(self, features_path: Path) -> tuple[dict[str, object], ...]: ...


class _WriteRuntimeScenarioOverride(Protocol):
    def __call__(
        self,
        *,
        scenario_path: Path,
        features_path: Path,
        output_dir: Path,
        agents_path: Path | None,
    ) -> Path: ...


class _TruthLabel(Protocol):
    def __call__(self, snapshot_root: Path, *, decision_date: date) -> str | None: ...


class _LoadKrxClose(Protocol):
    def __call__(self, snapshot_root: Path, trading_date: date) -> float | None: ...


class _SummaryLike(Protocol):
    def to_mapping(self) -> dict[str, object]: ...


class _Summarize(Protocol):
    def __call__(self, rows: list[object]) -> _SummaryLike: ...


class _RequireDate(Protocol):
    def __call__(self, row: dict[str, object], key: str) -> date: ...


class _RequireFloatField(Protocol):
    def __call__(self, row: dict[str, object], key: str) -> float: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
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


def _require_model_label(value: object) -> ModelLabel:
    if value not in {"up", "down", "skip"}:
        raise ValueError(f"unexpected model label: {value}")
    return cast(ModelLabel, value)


def _require_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"unexpected numeric value: {value}")
    return float(value)


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


def _decision_invoker_factory() -> _ScenarioInvoker:
    def fake_scenario_invoker(
        scenario_path: Path | str,
        decision_date: date,
        features_path: Path | None,
        output_dir: Path | None,
    ) -> DecisionResult:
        assert output_dir is not None
        assert Path(scenario_path).is_file()
        assert features_path is not None
        rows = READ_TABLE(features_path).to_pylist()
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
            label=_require_model_label(current_row["expected_decision"]),
            aggregate_score=_require_float(current_row["marker"]),
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


def test_backtest_runner_rejects_empty_features_and_duplicate_dates(tmp_path: Path) -> None:
    from kospi_decision_pipeline_app_kr_kospi.backtest import runner as runner_module

    load_feature_rows = cast(_LoadFeatureRows, getattr(runner_module, "_load_feature_rows"))
    empty_path = tmp_path / "empty.parquet"
    duplicate_path = tmp_path / "duplicate.parquet"
    _write_parquet(empty_path, [])
    _write_parquet(
        duplicate_path,
        [
            {"as_of_date": date(2025, 2, 3)},
            {"as_of_date": date(2025, 2, 3)},
        ],
    )

    with pytest.raises(ValueError, match="features parquet must not be empty"):
        load_feature_rows(empty_path)
    with pytest.raises(ValueError, match="expected unique as_of_date values in gold features"):
        load_feature_rows(duplicate_path)


def test_backtest_runner_validates_scenario_runtime_shape_and_optional_agents(
    tmp_path: Path,
) -> None:
    from kospi_decision_pipeline_app_kr_kospi.backtest import runner as runner_module

    write_runtime_scenario_override = cast(
        _WriteRuntimeScenarioOverride,
        getattr(runner_module, "_write_runtime_scenario_override"),
    )
    scenario_path = tmp_path / "scenario.yaml"
    features_path = tmp_path / "gold.parquet"
    output_dir = tmp_path / "out"
    _ = scenario_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="scenario payload must be a mapping"):
        write_runtime_scenario_override(
            scenario_path=scenario_path,
            features_path=features_path,
            output_dir=output_dir,
            agents_path=None,
        )

    _write_yaml(scenario_path, {"scenario_id": "broken"})
    _write_parquet(features_path, [{"as_of_date": date(2025, 2, 3)}])

    with pytest.raises(ValueError, match="runtime must be a mapping"):
        write_runtime_scenario_override(
            scenario_path=scenario_path,
            features_path=features_path,
            output_dir=output_dir,
            agents_path=None,
        )

    _write_yaml(
        scenario_path,
        {
            "scenario_id": "kospi.next_day",
            "runtime": {
                "agents_config_path": "agents.yaml",
                "features_path": "old.parquet",
                "output_dir": "old-out",
            },
        },
    )
    override_path = write_runtime_scenario_override(
        scenario_path=scenario_path,
        features_path=features_path,
        output_dir=output_dir,
        agents_path=None,
    )
    payload = yaml.safe_load(override_path.read_text(encoding="utf-8"))
    assert payload["runtime"]["features_path"] == str(features_path)
    assert payload["runtime"]["output_dir"] == str(output_dir)
    assert payload["runtime"]["agents_config_path"] == "agents.yaml"


def test_backtest_runner_validates_bronze_truth_inputs(tmp_path: Path) -> None:
    from kospi_decision_pipeline_app_kr_kospi.backtest import runner as runner_module

    truth_label = cast(_TruthLabel, getattr(runner_module, "_truth_label"))
    load_krx_close = cast(_LoadKrxClose, getattr(runner_module, "_load_krx_close"))
    snapshot_root = tmp_path / "snapshot-root"
    _write_krx_close(snapshot_root, date(2025, 2, 4), 100.0)

    with pytest.raises(ValueError, match="missing KRX close for 2025-02-03"):
        truth_label(snapshot_root, decision_date=date(2025, 2, 3))

    _write_krx_close(snapshot_root, date(2025, 2, 3), 0.0)
    with pytest.raises(ValueError, match="KRX closes must be positive"):
        truth_label(snapshot_root, decision_date=date(2025, 2, 3))

    multirow_path = snapshot_root / "krx" / "kospi_index" / "2025-02-05.parquet"
    _write_parquet(
        multirow_path,
        [
            {"trade_date": date(2025, 2, 5), "close": 100.0},
            {"trade_date": date(2025, 2, 5), "close": 101.0},
        ],
    )
    with pytest.raises(ValueError, match="expected exactly one KRX row for 2025-02-05"):
        load_krx_close(snapshot_root, date(2025, 2, 5))


def test_backtest_runner_rejects_non_evaluable_run_and_invalid_scalars(tmp_path: Path) -> None:
    from kospi_decision_pipeline_app_kr_kospi.backtest import runner as runner_module

    summarize = cast(_Summarize, getattr(runner_module, "_summarize"))
    require_date = cast(_RequireDate, getattr(runner_module, "_require_date"))
    require_float_field = cast(_RequireFloatField, getattr(runner_module, "_require_float"))
    features_path = tmp_path / "gold" / "decision_features.parquet"
    snapshot_root = tmp_path / "snapshot-root"
    output_dir = tmp_path / "backtest"
    scenario_path = tmp_path / "scenario.yaml"
    agents_path = tmp_path / "agents.yaml"
    _write_parquet(
        features_path, [{"as_of_date": date(2025, 2, 3), "expected_decision": "skip", "marker": 1}]
    )
    _write_krx_close(snapshot_root, date(2025, 2, 3), 100.0)
    _write_yaml(
        agents_path, {"weights": {}, "thresholds": {"up": 0.25, "down": -0.25}, "agents": {}}
    )
    _write_yaml(scenario_path, _scenario_payload(agents_path, features_path, output_dir))

    with pytest.raises(ValueError, match="backtest produced no evaluable rows"):
        runner_module.run_backtest(
            features_path=features_path,
            snapshot_root=snapshot_root,
            output_dir=output_dir,
            scenario_path=scenario_path,
            agents_path=agents_path,
            scenario_invoker=_decision_invoker_factory(),
        )

    assert summarize([]).to_mapping() == {
        "evaluated_count": 0,
        "hit_count": 0,
        "skip_count": 0,
        "hit_rate": None,
        "skip_rate": None,
        "hit_rate_denominator": "evaluated_count - skip_count (skip excluded)",
    }
    with pytest.raises(ValueError, match="as_of_date must be a date"):
        require_date({"as_of_date": "2025-02-03"}, "as_of_date")
    with pytest.raises(ValueError, match="close must be a numeric scalar"):
        require_float_field({"close": object()}, "close")
