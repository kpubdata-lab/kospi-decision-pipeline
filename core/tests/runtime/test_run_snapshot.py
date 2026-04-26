from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from kospi_decision_pipeline_core.runtime.service import run_kospi_snapshot


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


def test_run_kospi_snapshot_writes_all_runnable_days_and_uses_config_thresholds(
    tmp_path: Path,
) -> None:
    agents_payload = _agents_payload()
    agents_payload["thresholds"] = {"up": 1.0, "down": -1.0}
    _write_yaml(tmp_path / "config" / "agents.yaml", agents_payload)
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(
        features_path,
        [_feature_row(date(2025, 2, 13)), _feature_row(date(2025, 2, 14))],
    )

    results = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")

    assert tuple(result.decision_date for result in results) == (
        date(2025, 2, 14),
        date(2025, 2, 17),
    )
    assert all(result.label == "skip" for result in results)
    assert all(result.threshold_up == 1.0 for result in results)
    assert all(result.threshold_down == -1.0 for result in results)
    assert all(len(result.votes) == 5 for result in results)
    assert all(
        tuple(vote.agent_name for vote in result.votes)
        == ("domestic_macro", "flow", "technical", "valuation", "volatility")
        for result in results
    )
    assert (tmp_path / "out" / "kospi.next_day" / "2025-02-14.jsonl").is_file()
    assert (tmp_path / "out" / "kospi.next_day" / "2025-02-17.jsonl").is_file()


def test_run_kospi_snapshot_skips_exchange_holidays_in_decision_dates(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(features_path, [_feature_row(date(2025, 5, 2))])

    results = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")

    assert tuple(result.decision_date for result in results) == (date(2025, 5, 7),)


def test_run_kospi_snapshot_rejects_forbidden_runtime_columns(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    row = _feature_row(date(2025, 2, 13))
    row["target_direction_label"] = "up"
    _write_features(features_path, [row])

    with pytest.raises(ValueError, match="forbidden columns detected"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_rejects_empty_snapshot(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(features_path, [])

    with pytest.raises(ValueError, match="produced no runnable decision rows"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_rejects_duplicate_decision_dates(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(
        features_path,
        [
            {
                **_feature_row(date(2025, 2, 13)),
                "decision_date": date(2025, 2, 14),
            },
            {
                **_feature_row(date(2025, 2, 12)),
                "decision_date": date(2025, 2, 14),
            },
        ],
    )

    with pytest.raises(ValueError, match="expected unique decision_date values"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_validates_runtime_decision_date_types(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    _write_features(
        features_path,
        [
            {
                **_feature_row(date(2025, 2, 13)),
                "decision_date": "2025-02-14",
            }
        ],
    )

    with pytest.raises(ValueError, match="decision_date must be a date"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_rejects_decision_date_only_rows(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    row = _feature_row(date(2025, 2, 13))
    del row["as_of_date"]
    row["decision_date"] = date(2025, 2, 14)
    _write_features(features_path, [row])

    with pytest.raises(ValueError, match="must include provenance as_of_date or trade_date"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_requires_as_of_or_decision_date(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    row = _feature_row(date(2025, 2, 13))
    del row["as_of_date"]
    _write_features(features_path, [row])

    with pytest.raises(ValueError, match="must include as_of_date or decision_date"):
        _ = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")


def test_run_kospi_snapshot_preserves_explicit_snapshot_id(tmp_path: Path) -> None:
    _write_yaml(tmp_path / "config" / "agents.yaml", _agents_payload())
    scenario_path = _write_yaml(tmp_path / "config" / "scenario.yaml", _scenario_payload(tmp_path))
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    row = _feature_row(date(2025, 2, 13))
    row["snapshot_id"] = "gold-snapshot-2025-02-13"
    _write_features(features_path, [row])

    results = run_kospi_snapshot(scenario_path, features_path, tmp_path / "out")

    assert tuple(result.snapshot_id for result in results) == ("gold-snapshot-2025-02-13",)
