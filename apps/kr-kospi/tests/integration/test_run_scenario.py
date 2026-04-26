from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from kospi_decision_pipeline_app_kr_kospi.cli import main
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


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_features(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def test_run_scenario_cli_end_to_end(tmp_path: Path) -> None:
    agents_path = tmp_path / "config" / "agents.yaml"
    scenario_path = tmp_path / "config" / "scenario.yaml"
    features_path = tmp_path / "data" / "gold" / "features.parquet"
    output_root = tmp_path / "data" / "decisions"
    _write_yaml(
        agents_path,
        {
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
        },
    )
    _write_yaml(
        scenario_path,
        {
            "scenario_id": "kospi.next_day",
            "horizon": "next_day",
            "agents": [
                "technical",
                "domestic_macro",
                "flow",
                "valuation",
                "volatility",
                "decision",
            ],
            "runtime": {
                "agents_config_path": str(agents_path),
                "features_path": str(features_path),
                "output_dir": str(output_root),
            },
        },
    )
    _write_features(
        features_path,
        [
            {
                "as_of_date": date(2025, 2, 13),
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
        ],
    )

    assert (
        main(
            [
                "run-scenario",
                "--date",
                "2025-02-14",
                "--scenario",
                str(scenario_path),
                "--features",
                str(features_path),
                "--out",
                str(output_root),
            ]
        )
        == 0
    )

    line = (output_root / "kospi.next_day" / "2025-02-14.jsonl").read_text(encoding="utf-8").strip()
    assert parse_decision_result(line).decision_date == date(2025, 2, 14)
