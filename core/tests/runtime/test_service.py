from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from kospi_decision_pipeline_core.runtime.service import run_kospi_scenario
from kospi_decision_pipeline_core.runtime import service as service_module
from kospi_decision_pipeline_core.schemas import DecisionResult
from kospi_decision_pipeline_core.schemas.serialization import parse_decision_result


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


def _write_features(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _agents_payload() -> dict[str, object]:
    return {
        "weights": {
            "technical": 0.30,
            "domestic_macro": 0.20,
            "flow": 0.25,
            "valuation": 0.10,
            "volatility": 0.15,
        },
        "thresholds": {"up": 0.25, "down": -0.25},
        "agents": {
            "technical": {
                "rule_version": "technical@1.0.0",
                "thresholds": {
                    "ma5_gap_up_min": 0.005,
                    "close_position_up_min": 0.60,
                    "return_5d_up_min": 0.010,
                    "ma5_gap_down_max": -0.005,
                    "close_position_down_max": 0.40,
                    "return_5d_down_max": -0.010,
                },
            },
            "domestic_macro": {
                "rule_version": "domestic_macro@1.0.0",
                "thresholds": {
                    "bok_rate_change_up_max": 0.00,
                    "usdkrw_return_5d_up_max": 0.010,
                    "bond_yield_change_30d_up_max": 0.05,
                    "bok_rate_change_down_min": 0.25,
                    "usdkrw_return_5d_down_min": 0.020,
                    "bond_yield_change_30d_down_min": 0.10,
                    "usdkrw_return_5d_mixed_pos_min": 0.015,
                    "usdkrw_return_5d_mixed_neg_max": -0.015,
                    "bond_yield_change_30d_mixed_pos_min": 0.05,
                    "bond_yield_change_30d_mixed_neg_max": 0.00,
                },
            },
            "flow": {
                "rule_version": "flow@1.0.0",
                "thresholds": {
                    "foreign_pct_up_min": 0.010,
                    "foreign_pct_down_max": -0.010,
                    "foreign_pct_neutral_abs_max": 0.003,
                },
            },
            "valuation": {
                "rule_version": "valuation@1.0.0",
                "thresholds": {
                    "per_percentile_up_max": 0.30,
                    "pbr_percentile_up_max": 0.30,
                    "per_percentile_down_min": 0.70,
                    "pbr_percentile_down_min": 0.70,
                    "fair_value_center": 0.50,
                    "fair_value_half_band": 0.10,
                },
            },
            "volatility": {
                "rule_version": "volatility@1.0.0",
                "thresholds": {
                    "realized_vol_20d_up_max": 0.18,
                    "realized_vol_pct_up_max": 0.30,
                    "atr_14d_up_max": 35.0,
                    "realized_vol_pct_down_min": 0.80,
                    "realized_vol_20d_down_min": 0.25,
                    "atr_14d_down_min": 45.0,
                    "realized_vol_pct_mid_low": 0.30,
                    "realized_vol_pct_mid_high": 0.80,
                },
            },
        },
    }


def _scenario_payload(root: Path) -> dict[str, object]:
    return {
        "scenario_id": "kospi.next_day",
        "horizon": "next_day",
        "agents": ["technical", "domestic_macro", "flow", "valuation", "volatility", "decision"],
        "runtime": {
            "agents_config_path": str(root / "config" / "agents.yaml"),
            "features_path": str(root / "data" / "gold" / "features.parquet"),
            "output_dir": str(root / "data" / "decisions"),
        },
    }


def _feature_row(as_of_date: date) -> dict[str, object]:
    return {
        "as_of_date": as_of_date,
        "kospi_return_1d": 0.01,
        "kospi_return_5d": 0.02,
        "kospi_ma5_gap": 0.01,
        "kospi_close_position": 0.75,
        "bok_base_rate_change_30d": 0.0,
        "usd_krw_return_5d": 0.0,
        "kr_bond_yield_change_30d": 0.0,
        "foreign_net_buy_krw_5d_sum": 10.0,
        "institution_net_buy_krw_5d_sum": 5.0,
        "individual_net_buy_krw_5d_sum": -15.0,
        "foreign_net_buy_5d_pct_of_turnover": 0.02,
        "kospi_per": 10.0,
        "kospi_pbr": 1.0,
        "kospi_per_percentile_252d": 0.2,
        "kospi_pbr_percentile_252d": 0.2,
        "kospi_realized_vol_20d": 0.15,
        "kospi_realized_vol_20d_percentile_252d": 0.2,
        "kospi_atr_14d": 12.0,
    }


def test_run_kospi_scenario_writes_single_jsonl_and_round_trips(tmp_path: Path) -> None:
    agents_path = _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(features_path, [_feature_row(date(2025, 2, 13))])

    result = run_kospi_scenario(scenario_path, date(2025, 2, 14))

    output_path = tmp_path / "data" / "decisions" / "kospi.next_day" / "2025-02-14.jsonl"
    assert isinstance(result, DecisionResult)
    assert output_path.is_file()
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert parse_decision_result(lines[0]) == result
    assert tuple(vote.agent_name for vote in result.votes) == (
        "domestic_macro",
        "flow",
        "technical",
        "valuation",
        "volatility",
    )
    assert result.snapshot_id
    assert agents_path.is_file()


def test_run_kospi_scenario_rejects_missing_or_duplicate_effective_feature_rows(
    tmp_path: Path,
) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"

    _write_features(features_path, [])
    with pytest.raises(ValueError, match="expected exactly one features row"):
        _ = run_kospi_scenario(scenario_path, date(2025, 2, 14))

    _write_features(
        features_path,
        [_feature_row(date(2025, 2, 13)), _feature_row(date(2025, 2, 13))],
    )
    with pytest.raises(ValueError, match="expected exactly one features row"):
        _ = run_kospi_scenario(scenario_path, date(2025, 2, 14))


def test_run_kospi_scenario_rejects_leakage_before_persisting_output(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(features_path, [_feature_row(date(2025, 2, 14))])

    with pytest.raises(ValueError, match="decision_date"):
        _ = run_kospi_scenario(scenario_path, date(2025, 2, 14))

    assert not (tmp_path / "data" / "decisions" / "kospi.next_day" / "2025-02-14.jsonl").exists()


def test_service_helper_paths_and_feature_filters(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir(parents=True)
    _ = (project_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    scenario_path = project_root / "apps" / "kr-kospi" / "config" / "scenario.yaml"
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text("scenario_id: demo\n", encoding="utf-8")

    assert (
        service_module._resolve_path(scenario_path, "data/gold/features.parquet", None)
        == project_root / "data/gold/features.parquet"
    )
    assert service_module._workspace_root(scenario_path) == project_root
    assert service_module._matching_rows(
        [{"decision_date": date(2025, 2, 14), "value": 1.0}],
        date(2025, 2, 14),
    ) == [{"decision_date": date(2025, 2, 14), "value": 1.0}]
    assert service_module._previous_trading_day(date(2025, 2, 17)) == date(2025, 2, 14)
    assert (
        service_module._resolve_path(
            scenario_path,
            "data/gold/features.parquet",
            project_root / "override.parquet",
        )
        == project_root / "override.parquet"
    )
    assert service_module._resolve_snapshot_id({"value": 1.0}).startswith("gold:")


def test_service_helper_fallback_root_and_snapshot_without_date(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.yaml"
    _ = scenario_path.write_text("scenario_id: demo\n", encoding="utf-8")

    assert service_module._workspace_root(scenario_path) == tmp_path
    assert service_module._resolve_snapshot_id({"other": object()}).startswith("gold:")


def test_service_helper_validates_alignment_and_persistence_branches(tmp_path: Path) -> None:
    service_module._assert_lag_safe_row({"decision_date": date(2025, 2, 14)}, date(2025, 2, 14))

    with pytest.raises(ValueError, match="valid as_of_date"):
        service_module._assert_lag_safe_row({"as_of_date": "2025-02-13"}, date(2025, 2, 14))

    with pytest.raises(ValueError, match="strictly earlier than decision_date"):
        service_module._assert_lag_safe_row({"as_of_date": date(2025, 2, 14)}, date(2025, 2, 14))

    snapshot_id = service_module._resolve_snapshot_id({"snapshot_id": "explicit-snapshot"})
    assert snapshot_id == "explicit-snapshot"

    result = DecisionResult(
        decision_date=date(2025, 2, 14),
        label="skip",
        aggregate_score=0.0,
        threshold_up=0.25,
        threshold_down=-0.25,
        votes=(),
        config_signature="config-signature",
        snapshot_id="snapshot-id",
    )
    service_module._persist_decision_result(result, tmp_path / "out", "kospi.next_day")
    assert (
        parse_decision_result(
            (tmp_path / "out" / "kospi.next_day" / "2025-02-14.jsonl")
            .read_text(encoding="utf-8")
            .strip()
        )
        == result
    )


def test_run_kospi_scenario_raises_if_runner_finishes_without_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(features_path, [_feature_row(date(2025, 2, 13))])

    class _FakeRun:
        def __init__(self) -> None:
            self.final_state = type(
                "FinalState",
                (),
                {"segments": [type("Segment", (), {"decision_result": None})()]},
            )()

    class _FakeRunner:
        def __init__(self, **_: object) -> None:
            pass

        def run(self, _scenario: object) -> _FakeRun:
            return _FakeRun()

    monkeypatch.setattr(service_module, "ScenarioRunner", _FakeRunner)

    with pytest.raises(ValueError, match="did not produce a final decision result"):
        _ = run_kospi_scenario(scenario_path, date(2025, 2, 14))
