from __future__ import annotations

from decimal import Decimal
from datetime import date
from math import log
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq

from .gold_features import assert_no_forbidden_gold_columns


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...

    def slice(self, offset: int, length: int | None = None) -> _ArrowTable: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))
FEATURE_COLUMNS = (
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
)
TARGET_COLUMNS = (
    "target_next_day_simple_return",
    "target_next_day_log_return",
    "target_direction_label",
)
OUTPUT_COLUMNS = ("trade_date", *FEATURE_COLUMNS, *TARGET_COLUMNS)
EMPTY_ROW = {
    "trade_date": date(1970, 1, 1),
    **{column_name: 0.0 for column_name in FEATURE_COLUMNS},
    "target_next_day_simple_return": 0.0,
    "target_next_day_log_return": 0.0,
    "target_direction_label": "",
}


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    if rows:
        return factory.from_pylist(rows)
    return factory.from_pylist([cast(dict[str, object], EMPTY_ROW)]).slice(0, 0)


def _float_value(row: dict[str, object], field_name: str) -> float | None:
    value = row.get(field_name)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal | str):
        return float(value)
    return None


def _trade_date_value(row: dict[str, object]) -> date:
    value = row.get("trade_date", row.get("as_of_date"))
    if not isinstance(value, date):
        raise ValueError(f"missing or invalid trade date: {value}")
    return value


def _target_direction_label(
    target_next_day_log_return: float,
    *,
    flat_band_abs_log_return: float,
) -> str:
    if target_next_day_log_return >= flat_band_abs_log_return:
        return "up"
    if target_next_day_log_return <= -flat_band_abs_log_return:
        return "down"
    return "flat"


def _read_gold_rows(gold_dir: Path) -> list[dict[str, object]]:
    if gold_dir.is_file():
        parquet_paths = (gold_dir,)
    else:
        parquet_paths = tuple(sorted(gold_dir.rglob("*.parquet")))
    rows: list[dict[str, object]] = []
    for parquet_path in parquet_paths:
        table = READ_TABLE(parquet_path)
        parquet_rows = table.to_pylist()
        assert_no_forbidden_gold_columns(parquet_rows[0].keys() if parquet_rows else ())
        rows.extend(parquet_rows)
    return rows


def _sorted_gold_rows(gold_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    sorted_rows = sorted(gold_rows, key=_trade_date_value)
    for index in range(1, len(sorted_rows)):
        if _trade_date_value(sorted_rows[index]) == _trade_date_value(sorted_rows[index - 1]):
            raise ValueError("duplicate trade_date in gold dataset")
    return sorted_rows


def _build_output_row(
    current_row: dict[str, object],
    *,
    target_next_day_simple_return: float,
    target_next_day_log_return: float,
    target_direction_label: str,
) -> dict[str, object]:
    output_row: dict[str, object] = {"trade_date": _trade_date_value(current_row)}
    for column_name in FEATURE_COLUMNS:
        output_row[column_name] = current_row[column_name]
    output_row["target_next_day_simple_return"] = target_next_day_simple_return
    output_row["target_next_day_log_return"] = target_next_day_log_return
    output_row["target_direction_label"] = target_direction_label
    return output_row


def build_backtest_dataset(
    gold_dir: Path,
    output_path: Path,
    *,
    flat_band_abs_log_return: float = 0.001,
) -> Path:
    gold_rows = _sorted_gold_rows(_read_gold_rows(gold_dir))
    backtest_rows: list[dict[str, object]] = []
    for index, current_row in enumerate(gold_rows[:-1]):
        next_row = gold_rows[index + 1]
        current_close = _float_value(current_row, "kospi_close")
        next_close = _float_value(next_row, "kospi_close")
        if current_close is None or next_close is None or current_close <= 0.0 or next_close <= 0.0:
            continue
        target_next_day_simple_return = (next_close / current_close) - 1.0
        target_next_day_log_return = log(next_close / current_close)
        backtest_rows.append(
            _build_output_row(
                current_row,
                target_next_day_simple_return=target_next_day_simple_return,
                target_next_day_log_return=target_next_day_log_return,
                target_direction_label=_target_direction_label(
                    target_next_day_log_return,
                    flat_band_abs_log_return=flat_band_abs_log_return,
                ),
            )
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(backtest_rows), output_path, compression="snappy")
    return output_path


__all__ = [
    "FEATURE_COLUMNS",
    "OUTPUT_COLUMNS",
    "TARGET_COLUMNS",
    "build_backtest_dataset",
]
