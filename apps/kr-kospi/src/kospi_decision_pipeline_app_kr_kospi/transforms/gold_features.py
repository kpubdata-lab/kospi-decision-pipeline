from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
from math import sqrt
from pathlib import Path
from statistics import pstdev
from typing import Protocol, cast, final

import pyarrow as pa
import pyarrow.parquet as pq

from .calendar import TradingCalendar


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


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))
TRADING_DAYS_FOR_PERCENTILE = 252


@dataclass(frozen=True, slots=True)
class SilverDatasetRequirement:
    source_name: str
    dataset_id: str


@dataclass(frozen=True, slots=True)
class DailyInputs:
    as_of_date: date
    kospi_high: float
    kospi_low: float
    kospi_close: float
    turnover_krw: float
    foreign_net_buy_krw: float
    institution_net_buy_krw: float
    individual_net_buy_krw: float
    bok_base_rate: float
    usd_krw_close: float
    kr_bond_yield_3y: float
    kospi_per: float
    kospi_pbr: float


class GoldFeatureError(ValueError):
    pass


class MissingGoldInputError(GoldFeatureError):
    def __init__(self, dataset_id: str, as_of_date: date) -> None:
        super().__init__(
            f"missing required Silver input '{dataset_id}' for {as_of_date.isoformat()}"
        )


class InvalidGoldInputError(GoldFeatureError):
    def __init__(self, dataset_id: str, field_name: str, value: object) -> None:
        super().__init__(
            f"invalid Silver input for dataset '{dataset_id}' field '{field_name}': {value}"
        )


def _canonical_row_key(row: dict[str, object]) -> tuple[str, ...]:
    return tuple(f"{column}={row[column]}" for column in sorted(row))


def assert_no_forbidden_gold_columns(columns: Iterable[str]) -> None:
    forbidden = [name for name in columns if name.startswith(("target_", "future_"))]
    if forbidden:
        raise ValueError(f"forbidden columns in Gold output: {forbidden}")


def gold_sha256(path: Path) -> str:
    rows = READ_TABLE(path).to_pylist()
    canonical = "\n".join("|".join(_canonical_row_key(row)) for row in rows)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _float_value(row: dict[str, object], field_name: str, dataset_id: str) -> float:
    value = row.get(field_name)
    if value is None or isinstance(value, bool):
        raise InvalidGoldInputError(dataset_id, field_name, value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError as exc:
        raise InvalidGoldInputError(dataset_id, field_name, value) from exc


def _date_value(row: dict[str, object], field_name: str, dataset_id: str) -> date:
    value = row.get(field_name)
    if not isinstance(value, date):
        raise InvalidGoldInputError(dataset_id, field_name, value)
    return value


def _text_value(row: dict[str, object], field_name: str, dataset_id: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str):
        raise InvalidGoldInputError(dataset_id, field_name, value)
    return value


def _trading_days_between(start: date, end: date, calendar: TradingCalendar) -> tuple[date, ...]:
    current = start
    dates: list[date] = []
    while current <= end:
        if calendar.is_trading_day(current):
            dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def _percentile_rank(values: Sequence[float], current_value: float) -> float:
    count = sum(1 for value in values if value <= current_value)
    return count / len(values)


def _rolling_percentile(values: Sequence[float], index: int, *, window: int) -> float:
    window_values = values[(index - window + 1) : index + 1]
    return _percentile_rank(window_values, window_values[-1])


def _rolling_percentile_ignore_none(
    values: Sequence[float | None],
    index: int,
    *,
    window: int,
) -> float:
    filtered = [value for value in values[(index - window + 1) : index + 1] if value is not None]
    current_value = values[index]
    if current_value is None or not filtered:
        raise ValueError("current rolling value must be present")
    return _percentile_rank(filtered, current_value)


@final
class GoldFeatureBuilder:
    OUTPUT_FILE_NAME = "decision_features.parquet"
    REQUIRED_SILVER_DATASETS = (
        SilverDatasetRequirement("krx", "kospi_index"),
        SilverDatasetRequirement("krx", "investor_flow"),
        SilverDatasetRequirement("ecos", "base_rate"),
        SilverDatasetRequirement("ecos", "usd_krw"),
        SilverDatasetRequirement("ecos", "bond_yield"),
        SilverDatasetRequirement("krx", "market_valuation"),
    )

    _output_root: Path
    _calendar: TradingCalendar

    def __init__(self, output_root: Path, calendar: TradingCalendar | None = None) -> None:
        self._output_root = output_root
        self._calendar = TradingCalendar() if calendar is None else calendar

    def build(self, *, silver_root: Path, start: date, end: date) -> Path:
        trading_days = _trading_days_between(start, end, self._calendar)
        daily_inputs = [
            self._load_daily_inputs(silver_root, as_of_date) for as_of_date in trading_days
        ]
        gold_rows = self._build_rows(daily_inputs)
        output_path = self._output_root / self.OUTPUT_FILE_NAME
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table = _table_from_pylist(gold_rows)
        assert_no_forbidden_gold_columns(table.column_names)
        WRITE_TABLE(table, output_path, compression="snappy")
        return output_path

    def _load_daily_inputs(self, silver_root: Path, as_of_date: date) -> DailyInputs:
        kospi_index = self._read_required_row(silver_root, "kospi_index", as_of_date)
        investor_flow = self._read_required_row(silver_root, "investor_flow", as_of_date)
        base_rate = self._read_required_row(silver_root, "base_rate", as_of_date)
        usd_krw = self._read_required_row(silver_root, "usd_krw", as_of_date)
        bond_yield = self._read_bond_yield_row(silver_root, as_of_date)
        market_valuation = self._read_required_row(silver_root, "market_valuation", as_of_date)
        return DailyInputs(
            as_of_date=as_of_date,
            kospi_high=_float_value(kospi_index, "high", "kospi_index"),
            kospi_low=_float_value(kospi_index, "low", "kospi_index"),
            kospi_close=_float_value(kospi_index, "close", "kospi_index"),
            turnover_krw=_float_value(kospi_index, "turnover_krw", "kospi_index"),
            foreign_net_buy_krw=_float_value(investor_flow, "foreign_net_buy_krw", "investor_flow"),
            institution_net_buy_krw=_float_value(
                investor_flow, "institution_net_buy_krw", "investor_flow"
            ),
            individual_net_buy_krw=_float_value(
                investor_flow, "individual_net_buy_krw", "investor_flow"
            ),
            bok_base_rate=_float_value(base_rate, "base_rate_pct", "base_rate"),
            usd_krw_close=_float_value(usd_krw, "usd_krw_rate", "usd_krw"),
            kr_bond_yield_3y=_float_value(bond_yield, "yield_rate_pct", "bond_yield"),
            kospi_per=_float_value(market_valuation, "trailing_per", "market_valuation"),
            kospi_pbr=_float_value(market_valuation, "trailing_pbr", "market_valuation"),
        )

    def _read_required_row(
        self,
        silver_root: Path,
        dataset_id: str,
        as_of_date: date,
    ) -> dict[str, object]:
        path = silver_root / dataset_id / f"{as_of_date.isoformat()}.parquet"
        if not path.is_file():
            raise MissingGoldInputError(dataset_id, as_of_date)
        rows = READ_TABLE(path).to_pylist()
        if len(rows) != 1:
            raise InvalidGoldInputError(dataset_id, "row_count", len(rows))
        row = rows[0]
        row_date = _date_value(row, "as_of_date", dataset_id)
        if row_date != as_of_date:
            raise InvalidGoldInputError(dataset_id, "as_of_date", row_date)
        return row

    def _read_bond_yield_row(self, silver_root: Path, as_of_date: date) -> dict[str, object]:
        path = silver_root / "bond_yield" / f"{as_of_date.isoformat()}.parquet"
        if not path.is_file():
            raise MissingGoldInputError("bond_yield", as_of_date)
        rows = READ_TABLE(path).to_pylist()
        preferred_rows = [
            row for row in rows if _text_value(row, "maturity_code", "bond_yield") == "3Y"
        ]
        selected_rows = preferred_rows if preferred_rows else rows
        if len(selected_rows) != 1:
            raise InvalidGoldInputError("bond_yield", "maturity_code", selected_rows)
        row = selected_rows[0]
        row_date = _date_value(row, "as_of_date", "bond_yield")
        if row_date != as_of_date:
            raise InvalidGoldInputError("bond_yield", "as_of_date", row_date)
        return row

    def _build_rows(self, daily_inputs: Sequence[DailyInputs]) -> list[dict[str, object]]:
        closes = [row.kospi_close for row in daily_inputs]
        highs = [row.kospi_high for row in daily_inputs]
        lows = [row.kospi_low for row in daily_inputs]
        turnover = [row.turnover_krw for row in daily_inputs]
        base_rates = [row.bok_base_rate for row in daily_inputs]
        usd_krw_rates = [row.usd_krw_close for row in daily_inputs]
        bond_yields = [row.kr_bond_yield_3y for row in daily_inputs]
        foreign_flows = [row.foreign_net_buy_krw for row in daily_inputs]
        institution_flows = [row.institution_net_buy_krw for row in daily_inputs]
        individual_flows = [row.individual_net_buy_krw for row in daily_inputs]
        pers = [row.kospi_per for row in daily_inputs]
        pbrs = [row.kospi_pbr for row in daily_inputs]

        daily_returns: list[float | None] = [None]
        for index in range(1, len(daily_inputs)):
            daily_returns.append((closes[index] / closes[index - 1]) - 1.0)

        realized_vols: list[float | None] = []
        for index in range(len(daily_inputs)):
            if index < 20:
                realized_vols.append(None)
                continue
            trailing_returns = [
                value for value in daily_returns[(index - 19) : index + 1] if value is not None
            ]
            realized_vols.append(pstdev(trailing_returns) * sqrt(252.0))

        rows: list[dict[str, object]] = []
        for index in range(len(daily_inputs)):
            if index < TRADING_DAYS_FOR_PERCENTILE - 1:
                continue
            close_window = closes[(index - 19) : index + 1]
            close_window_min = min(close_window)
            close_window_max = max(close_window)
            close_position_denominator = close_window_max - close_window_min
            if close_position_denominator == 0.0:
                raise InvalidGoldInputError(
                    "kospi_index", "kospi_close_position_denominator", close_position_denominator
                )
            ma5 = sum(closes[(index - 4) : index + 1]) / 5.0
            realized_vol = realized_vols[index]
            if realized_vol is None:
                raise InvalidGoldInputError("kospi_index", "kospi_realized_vol_20d", realized_vol)
            row: dict[str, object] = {
                "as_of_date": daily_inputs[index].as_of_date,
                "kospi_close": closes[index],
                "kospi_return_1d": (closes[index] / closes[index - 1]) - 1.0,
                "kospi_return_3d": (closes[index] / closes[index - 3]) - 1.0,
                "kospi_return_5d": (closes[index] / closes[index - 5]) - 1.0,
                "kospi_ma5": ma5,
                "kospi_ma20": sum(close_window) / 20.0,
                "kospi_ma5_gap": (closes[index] - ma5) / ma5,
                "kospi_close_position": (closes[index] - close_window_min)
                / close_position_denominator,
                "bok_base_rate": base_rates[index],
                "bok_base_rate_change_30d": base_rates[index] - base_rates[index - 30],
                "usd_krw_close": usd_krw_rates[index],
                "usd_krw_return_5d": (usd_krw_rates[index] / usd_krw_rates[index - 5]) - 1.0,
                "kr_bond_yield_3y": bond_yields[index],
                "kr_bond_yield_change_30d": bond_yields[index] - bond_yields[index - 30],
                "foreign_net_buy_krw_5d_sum": sum(foreign_flows[(index - 4) : index + 1]),
                "institution_net_buy_krw_5d_sum": sum(institution_flows[(index - 4) : index + 1]),
                "individual_net_buy_krw_5d_sum": sum(individual_flows[(index - 4) : index + 1]),
                "foreign_net_buy_5d_pct_of_turnover": sum(foreign_flows[(index - 4) : index + 1])
                / sum(turnover[(index - 4) : index + 1]),
                "kospi_per": pers[index],
                "kospi_pbr": pbrs[index],
                "kospi_per_percentile_252d": _rolling_percentile(
                    pers, index, window=TRADING_DAYS_FOR_PERCENTILE
                ),
                "kospi_pbr_percentile_252d": _rolling_percentile(
                    pbrs, index, window=TRADING_DAYS_FOR_PERCENTILE
                ),
                "kospi_realized_vol_20d": realized_vol,
                "kospi_realized_vol_20d_percentile_252d": _rolling_percentile_ignore_none(
                    realized_vols, index, window=TRADING_DAYS_FOR_PERCENTILE
                ),
                "kospi_atr_14d": sum(
                    highs[inner_index] - lows[inner_index]
                    for inner_index in range(index - 13, index + 1)
                )
                / 14.0,
            }
            assert_no_forbidden_gold_columns(row.keys())
            rows.append(row)
        return rows


__all__ = [
    "GoldFeatureBuilder",
    "GoldFeatureError",
    "InvalidGoldInputError",
    "MissingGoldInputError",
    "SilverDatasetRequirement",
    "TRADING_DAYS_FOR_PERCENTILE",
    "assert_no_forbidden_gold_columns",
    "gold_sha256",
]
