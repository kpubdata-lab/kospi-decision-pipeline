from __future__ import annotations

from datetime import date, timedelta
from math import exp, log
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_app_kr_kospi.transforms import target_labels
from kospi_decision_pipeline_app_kr_kospi.transforms.target_labels import (
    build_backtest_dataset,
)


class _ArrowTable(Protocol):
    @property
    def column_names(self) -> list[str]: ...

    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


class _FloatValue(Protocol):
    def __call__(self, row: dict[str, object], field_name: str) -> float | None: ...


class _TradeDateValue(Protocol):
    def __call__(self, row: dict[str, object]) -> date: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


EXPECTED_COLUMNS = [
    "trade_date",
    "kospi_close",
    "kospi_return_1d",
    "kospi_return_3d",
    "kospi_return_5d",
    "kospi_ma5",
    "kospi_ma20",
    "kospi_ma5_gap",
    "kospi_close_position",
    "bok_base_rate",
    "bok_base_rate_change_30d",
    "usd_krw_close",
    "usd_krw_return_5d",
    "kr_bond_yield_3y",
    "kr_bond_yield_change_30d",
    "foreign_net_buy_krw_5d_sum",
    "institution_net_buy_krw_5d_sum",
    "individual_net_buy_krw_5d_sum",
    "foreign_net_buy_5d_pct_of_turnover",
    "kospi_per",
    "kospi_pbr",
    "kospi_per_percentile_252d",
    "kospi_pbr_percentile_252d",
    "kospi_realized_vol_20d",
    "kospi_realized_vol_20d_percentile_252d",
    "kospi_atr_14d",
    "target_next_day_simple_return",
    "target_next_day_log_return",
    "target_direction_label",
]


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


def _write_gold_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def _read_rows(path: Path) -> list[dict[str, object]]:
    return READ_TABLE(path).to_pylist()


def _feature_row(trade_date: date, close: float) -> dict[str, object]:
    return {
        "as_of_date": trade_date,
        "kospi_close": close,
        "kospi_return_1d": 0.01,
        "kospi_return_3d": 0.02,
        "kospi_return_5d": 0.03,
        "kospi_ma5": close - 1.0,
        "kospi_ma20": close - 2.0,
        "kospi_ma5_gap": 0.001,
        "kospi_close_position": 0.5,
        "bok_base_rate": 3.5,
        "bok_base_rate_change_30d": 0.1,
        "usd_krw_close": 1320.0,
        "usd_krw_return_5d": -0.01,
        "kr_bond_yield_3y": 3.1,
        "kr_bond_yield_change_30d": 0.05,
        "foreign_net_buy_krw_5d_sum": 10.0,
        "institution_net_buy_krw_5d_sum": 11.0,
        "individual_net_buy_krw_5d_sum": -21.0,
        "foreign_net_buy_5d_pct_of_turnover": 0.02,
        "kospi_per": 10.5,
        "kospi_pbr": 1.1,
        "kospi_per_percentile_252d": 0.4,
        "kospi_pbr_percentile_252d": 0.5,
        "kospi_realized_vol_20d": 0.16,
        "kospi_realized_vol_20d_percentile_252d": 0.6,
        "kospi_atr_14d": 12.0,
    }


def test_build_backtest_dataset_computes_targets_with_spec_column_order(tmp_path: Path) -> None:
    gold_dir = tmp_path / "data" / "gold" / "decision_features"
    output_path = tmp_path / "data" / "gold" / "backtest_dataset.parquet"
    start = date(2024, 1, 2)
    closes = [
        100.0,
        100.0 * exp(0.001),
        100.0,
        100.0 * exp(0.0005),
        100.0 * exp(0.0025),
    ]
    source_rows = [
        _feature_row(start + timedelta(days=index), close) for index, close in enumerate(closes)
    ]
    assert all(not column.startswith("target_") for column in source_rows[0])
    _write_gold_rows(gold_dir / "part-000.parquet", list(reversed(source_rows)))

    written_path = build_backtest_dataset(gold_dir, output_path)

    rows = _read_rows(written_path)
    table = READ_TABLE(written_path)

    assert written_path == output_path
    assert table.column_names == EXPECTED_COLUMNS
    assert [row["trade_date"] for row in rows] == [
        start,
        start + timedelta(days=1),
        start + timedelta(days=2),
        start + timedelta(days=3),
    ]
    assert [row["target_direction_label"] for row in rows] == ["up", "down", "flat", "up"]
    assert abs(cast(float, rows[0]["target_next_day_log_return"]) - 0.001) < 1e-12
    assert abs(cast(float, rows[1]["target_next_day_log_return"]) + 0.001) < 1e-12
    assert abs(cast(float, rows[2]["target_next_day_log_return"]) - 0.0005) < 1e-12
    assert abs(cast(float, rows[0]["target_next_day_simple_return"]) - (exp(0.001) - 1.0)) < 1e-12
    assert abs(cast(float, rows[1]["target_next_day_simple_return"]) - (exp(-0.001) - 1.0)) < 1e-12
    assert abs(cast(float, rows[2]["target_next_day_simple_return"]) - (exp(0.0005) - 1.0)) < 1e-12
    assert all(not key.startswith("future_") for key in rows[0])
    assert sorted(key for key in rows[0] if key.startswith("target_")) == [
        "target_direction_label",
        "target_next_day_log_return",
        "target_next_day_simple_return",
    ]


def test_build_backtest_dataset_drops_rows_with_missing_next_day_target_inputs(
    tmp_path: Path,
) -> None:
    gold_dir = tmp_path / "gold" / "decision_features"
    output_path = tmp_path / "gold" / "backtest_dataset.parquet"
    start = date(2024, 1, 2)
    source_rows = [
        _feature_row(start, 100.0),
        _feature_row(start + timedelta(days=1), 101.0),
        _feature_row(start + timedelta(days=2), 0.0),
    ]

    _write_gold_rows(gold_dir / "part-000.parquet", source_rows)

    rows = _read_rows(build_backtest_dataset(gold_dir, output_path))

    assert [row["trade_date"] for row in rows] == [start]
    assert abs(cast(float, rows[0]["target_next_day_log_return"]) - log(101.0 / 100.0)) < 1e-12


def test_build_backtest_dataset_accepts_single_parquet_file_and_writes_empty_output_schema(
    tmp_path: Path,
) -> None:
    gold_file = tmp_path / "decision_features.parquet"
    output_path = tmp_path / "backtest_dataset.parquet"

    _write_gold_rows(gold_file, [_feature_row(date(2024, 1, 2), 100.0)])

    written_path = build_backtest_dataset(gold_file, output_path)
    table = READ_TABLE(written_path)

    assert table.column_names == EXPECTED_COLUMNS
    assert table.to_pylist() == []


def test_target_label_helpers_handle_invalid_numeric_and_trade_date_inputs() -> None:
    float_value = cast(_FloatValue, getattr(target_labels, "_float_value"))
    trade_date_value = cast(_TradeDateValue, getattr(target_labels, "_trade_date_value"))

    assert float_value({"kospi_close": None}, "kospi_close") is None
    assert float_value({"kospi_close": True}, "kospi_close") is None
    assert float_value({"kospi_close": object()}, "kospi_close") is None
    with pytest.raises(ValueError, match="^missing or invalid trade date: None$"):
        _ = trade_date_value({})


def test_build_backtest_dataset_raises_for_duplicate_trade_dates(tmp_path: Path) -> None:
    gold_dir = tmp_path / "gold" / "decision_features"
    duplicate_day = date(2024, 1, 2)

    _write_gold_rows(
        gold_dir / "part-000.parquet",
        [
            _feature_row(duplicate_day, 100.0),
            _feature_row(duplicate_day, 101.0),
        ],
    )

    with pytest.raises(ValueError, match="^duplicate trade_date in gold dataset$"):
        _ = build_backtest_dataset(gold_dir, tmp_path / "gold" / "backtest_dataset.parquet")
