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
REALIZED_VOL_WINDOW = 20
ATR_WINDOW = 14


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


GoldRow = dict[str, date | float]


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


def _required_history_for_realized_vol_percentile() -> int:
    return REALIZED_VOL_WINDOW + TRADING_DAYS_FOR_PERCENTILE


def gold_warmup_trading_days() -> int:
    return _required_history_for_realized_vol_percentile() - 1


def gold_lookback_start(*, start: date, calendar: TradingCalendar) -> date:
    current = start
    remaining = gold_warmup_trading_days()
    while remaining > 0:
        current -= timedelta(days=1)
        if calendar.is_trading_day(current):
            remaining -= 1
    return current


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
        read_start = gold_lookback_start(start=start, calendar=self._calendar)
        trading_days = _trading_days_between(read_start, end, self._calendar)
        daily_inputs: list[DailyInputs | None] = []
        for as_of_date in trading_days:
            try:
                daily_inputs.append(self._load_daily_inputs(silver_root, as_of_date))
            except MissingGoldInputError:
                if as_of_date >= start:
                    raise
                daily_inputs.append(None)
        gold_rows = self._build_rows(daily_inputs, requested_start=start)
        output_path = self._output_root / self.OUTPUT_FILE_NAME
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table = _table_from_pylist(cast(list[dict[str, object]], gold_rows))
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
        if len(preferred_rows) != 1:
            raise InvalidGoldInputError("bond_yield", "maturity_code", rows)
        row = preferred_rows[0]
        row_date = _date_value(row, "as_of_date", "bond_yield")
        if row_date != as_of_date:
            raise InvalidGoldInputError("bond_yield", "as_of_date", row_date)
        return row

    def _build_rows(
        self,
        daily_inputs: Sequence[DailyInputs | None],
        *,
        requested_start: date,
    ) -> list[GoldRow]:
        rows: list[GoldRow] = []
        minimum_index = _required_history_for_realized_vol_percentile() - 1
        for index in range(len(daily_inputs)):
            if index < minimum_index:
                continue
            segment = daily_inputs[(index - minimum_index) : index + 1]
            if any(item is None for item in segment):
                continue
            valid_segment = cast(list[DailyInputs], segment)
            closes = [row.kospi_close for row in valid_segment]
            highs = [row.kospi_high for row in valid_segment]
            lows = [row.kospi_low for row in valid_segment]
            turnover = [row.turnover_krw for row in valid_segment]
            base_rates = [row.bok_base_rate for row in valid_segment]
            usd_krw_rates = [row.usd_krw_close for row in valid_segment]
            bond_yields = [row.kr_bond_yield_3y for row in valid_segment]
            foreign_flows = [row.foreign_net_buy_krw for row in valid_segment]
            institution_flows = [row.institution_net_buy_krw for row in valid_segment]
            individual_flows = [row.individual_net_buy_krw for row in valid_segment]
            pers = [row.kospi_per for row in valid_segment]
            pbrs = [row.kospi_pbr for row in valid_segment]
            local_index = len(valid_segment) - 1
            daily_returns = [
                (closes[return_index] / closes[return_index - 1]) - 1.0
                for return_index in range(1, len(valid_segment))
            ]
            realized_vols = [
                pstdev(daily_returns[(realized_index - REALIZED_VOL_WINDOW) : realized_index])
                * sqrt(252.0)
                for realized_index in range(REALIZED_VOL_WINDOW, len(valid_segment))
            ]
            close_window = closes[(local_index - 19) : local_index + 1]
            close_window_min = min(close_window)
            close_window_max = max(close_window)
            close_position_denominator = close_window_max - close_window_min
            if close_position_denominator == 0.0:
                raise InvalidGoldInputError(
                    "kospi_index", "kospi_close_position_denominator", close_position_denominator
                )
            ma5 = sum(closes[(local_index - 4) : local_index + 1]) / 5.0
            realized_vol = realized_vols[-1]
            row: GoldRow = {
                "as_of_date": valid_segment[-1].as_of_date,
                "kospi_close": closes[local_index],
                "kospi_return_1d": (closes[local_index] / closes[local_index - 1]) - 1.0,
                "kospi_return_3d": (closes[local_index] / closes[local_index - 3]) - 1.0,
                "kospi_return_5d": (closes[local_index] / closes[local_index - 5]) - 1.0,
                "kospi_ma5": ma5,
                "kospi_ma20": sum(close_window) / 20.0,
                "kospi_ma5_gap": (closes[local_index] - ma5) / ma5,
                "kospi_close_position": (closes[local_index] - close_window_min)
                / close_position_denominator,
                "bok_base_rate": base_rates[local_index],
                "bok_base_rate_change_30d": base_rates[local_index] - base_rates[local_index - 30],
                "usd_krw_close": usd_krw_rates[local_index],
                "usd_krw_return_5d": (usd_krw_rates[local_index] / usd_krw_rates[local_index - 5])
                - 1.0,
                "kr_bond_yield_3y": bond_yields[local_index],
                "kr_bond_yield_change_30d": bond_yields[local_index]
                - bond_yields[local_index - 30],
                "foreign_net_buy_krw_5d_sum": sum(
                    foreign_flows[(local_index - 4) : local_index + 1]
                ),
                "institution_net_buy_krw_5d_sum": sum(
                    institution_flows[(local_index - 4) : local_index + 1]
                ),
                "individual_net_buy_krw_5d_sum": sum(
                    individual_flows[(local_index - 4) : local_index + 1]
                ),
                "foreign_net_buy_5d_pct_of_turnover": sum(
                    foreign_flows[(local_index - 4) : local_index + 1]
                )
                / sum(turnover[(local_index - 4) : local_index + 1]),
                "institution_net_buy_5d_pct_of_turnover": sum(
                    institution_flows[(local_index - 4) : local_index + 1]
                )
                / sum(turnover[(local_index - 4) : local_index + 1]),
                "kospi_per": pers[local_index],
                "kospi_pbr": pbrs[local_index],
                "kospi_per_percentile_252d": _percentile_rank(
                    pers[-TRADING_DAYS_FOR_PERCENTILE:], pers[-1]
                ),
                "kospi_pbr_percentile_252d": _percentile_rank(
                    pbrs[-TRADING_DAYS_FOR_PERCENTILE:], pbrs[-1]
                ),
                "kospi_realized_vol_20d": realized_vol,
                "kospi_realized_vol_20d_percentile_252d": _percentile_rank(
                    realized_vols[-TRADING_DAYS_FOR_PERCENTILE:], realized_vol
                ),
                "kospi_atr_14d": sum(
                    highs[inner_index] - lows[inner_index]
                    for inner_index in range(local_index - 13, local_index + 1)
                )
                / 14.0,
            }
            assert_no_forbidden_gold_columns(row.keys())
            if valid_segment[-1].as_of_date >= requested_start:
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
    "gold_lookback_start",
    "gold_sha256",
    "gold_warmup_trading_days",
]
