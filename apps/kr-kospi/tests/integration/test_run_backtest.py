from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from kospi_decision_pipeline_app_kr_kospi.cli import main


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


def _write_dataset(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


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


def _scenario_payload(agents_path: Path, dataset_path: Path, output_dir: Path) -> dict[str, object]:
    return {
        "scenario_id": "kospi.next_day",
        "horizon": "next_day",
        "agents": ["technical", "domestic_macro", "flow", "valuation", "volatility", "decision"],
        "runtime": {
            "agents_config_path": str(agents_path),
            "features_path": str(dataset_path),
            "output_dir": str(output_dir),
        },
    }


def _backtest_dataset_rows() -> list[dict[str, object]]:
    start = date(2025, 2, 3)
    targets = ["down", "down", "up", "down", "up"]
    rows: list[dict[str, object]] = []
    for index, target in enumerate(targets):
        trade_date = start + timedelta(days=index)
        rows.append(
            {
                "trade_date": trade_date,
                "kospi_return_1d": 0.01,
                "kospi_return_3d": 0.015,
                "kospi_return_5d": 0.02,
                "kospi_ma5": 100.0 + index,
                "kospi_ma20": 98.0 + index,
                "kospi_ma5_gap": 0.01,
                "kospi_close_position": 0.75,
                "bok_base_rate": 3.0,
                "bok_base_rate_change_30d": 0.0,
                "usd_krw_close": 1300.0,
                "usd_krw_return_5d": 0.0,
                "kr_bond_yield_3y": 2.5,
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
                "target_next_day_simple_return": 0.01,
                "target_next_day_log_return": 0.01,
                "target_direction_label": target,
            }
        )
    return rows


def test_run_backtest_cli_end_to_end(tmp_path: Path) -> None:
    agents_path = tmp_path / "config" / "agents.yaml"
    dataset_path = tmp_path / "data" / "gold" / "backtest_dataset.parquet"
    first_output_dir = tmp_path / "out-first"
    second_output_dir = tmp_path / "out-second"
    scenario_path = tmp_path / "config" / "scenario.yaml"
    folds_path = tmp_path / "config" / "folds.yaml"
    _write_yaml(agents_path, _agents_payload())
    _write_dataset(dataset_path, _backtest_dataset_rows())
    _write_yaml(scenario_path, _scenario_payload(agents_path, dataset_path, first_output_dir))
    _write_yaml(folds_path, {"min_train_rows": 2, "test_fold_size": 2, "gap_days": 0})

    assert (
        main(
            [
                "run-backtest",
                "--dataset",
                str(dataset_path),
                "--scenario",
                str(scenario_path),
                "--out",
                str(first_output_dir),
                "--folds-config",
                str(folds_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run-backtest",
                "--dataset",
                str(dataset_path),
                "--scenario",
                str(scenario_path),
                "--out",
                str(second_output_dir),
                "--folds-config",
                str(folds_path),
            ]
        )
        == 0
    )

    assert (first_output_dir / "rows.jsonl").is_file()
    assert (first_output_dir / "metrics.json").is_file()
    assert (first_output_dir / "metrics.csv").is_file()
    assert (first_output_dir / "rows.jsonl").read_bytes() == (
        second_output_dir / "rows.jsonl"
    ).read_bytes()
    assert (first_output_dir / "metrics.json").read_bytes() == (
        second_output_dir / "metrics.json"
    ).read_bytes()

    rows_payload = [
        json.loads(line)
        for line in (first_output_dir / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [
        {
            "fold_id": row["fold_id"],
            "decision_date": row["decision_date"],
            "label": row["label"],
            "target_label": row["target_label"],
            "correct": row["correct"],
        }
        for row in rows_payload
    ] == [
        {
            "fold_id": 1,
            "decision_date": "2025-02-06",
            "label": "up",
            "target_label": "up",
            "correct": True,
        },
        {
            "fold_id": 1,
            "decision_date": "2025-02-07",
            "label": "up",
            "target_label": "down",
            "correct": False,
        },
        {
            "fold_id": 2,
            "decision_date": "2025-02-10",
            "label": "up",
            "target_label": "up",
            "correct": True,
        },
    ]
    assert all(
        isinstance(row["snapshot_id"], str) and row["snapshot_id"] != "" for row in rows_payload
    )
    assert all(
        row["config_signature"] == rows_payload[0]["config_signature"] for row in rows_payload
    )

    metrics_payload = json.loads((first_output_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics_payload["overall"] == {
        "fold_count": 2,
        "period_start": "2025-02-06",
        "period_end": "2025-02-10",
        "decision_count": 3,
        "hit_rate": 2 / 3,
        "precision_up": 2 / 3,
        "precision_down": None,
        "recall_up": 1.0,
        "recall_down": 0.0,
        "skip_rate": 0.0,
        "flat_rate": 0.0,
    }
    assert metrics_payload["folds"] == [
        {
            "fold_id": 1,
            "fold_start": "2025-02-06",
            "fold_end": "2025-02-07",
            "decision_count": 2,
            "hit_rate": 0.5,
            "precision_up": 0.5,
            "precision_down": None,
            "recall_up": 1.0,
            "recall_down": 0.0,
            "skip_rate": 0.0,
            "flat_rate": 0.0,
        },
        {
            "fold_id": 2,
            "fold_start": "2025-02-10",
            "fold_end": "2025-02-10",
            "decision_count": 1,
            "hit_rate": 1.0,
            "precision_up": 1.0,
            "precision_down": None,
            "recall_up": 1.0,
            "recall_down": None,
            "skip_rate": 0.0,
            "flat_rate": 0.0,
        },
    ]
