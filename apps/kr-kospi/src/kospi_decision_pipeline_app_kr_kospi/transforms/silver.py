from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from typing import Callable, Protocol, cast, final

import pyarrow as pa
import pyarrow.parquet as pq

from ..ingest.bronze import BronzeIngestResult
from ..ingest.manifests import read_manifest
from .calendar import TradingCalendar


SilverScalar = str | int | Decimal | date
SilverRow = dict[str, SilverScalar]
RawRow = dict[str, object]
_Normalizer = Callable[[RawRow], SilverRow]


class _ArrowTable(Protocol):
    @property
    def column_names(self) -> list[str]: ...

    def to_pylist(self) -> list[RawRow]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[RawRow | SilverRow]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


def _table_from_pylist(rows: list[RawRow | SilverRow]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


class SilverNormalizationError(ValueError):
    pass


class MissingFieldError(SilverNormalizationError):
    def __init__(self, dataset_id: str, field_name: str) -> None:
        super().__init__(f"missing field '{field_name}' for dataset '{dataset_id}'")


class InvalidValueError(SilverNormalizationError):
    def __init__(self, dataset_id: str, field_name: str, value: object) -> None:
        super().__init__(
            f"invalid value for field '{field_name}' in dataset '{dataset_id}': {value}"
        )


class NonTradingDayError(SilverNormalizationError):
    def __init__(self, dataset_id: str, value: date) -> None:
        super().__init__(f"non-trading day for dataset '{dataset_id}': {value.isoformat()}")


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    normalize_row: _Normalizer


@final
class SilverNormalizer:
    _output_root: Path
    _calendar: TradingCalendar

    def __init__(self, output_root: Path, calendar: TradingCalendar | None = None) -> None:
        self._output_root = output_root
        self._calendar = TradingCalendar() if calendar is None else calendar

    def normalize_parquet(self, bronze_path: Path) -> Path:
        source_name, dataset_id, partition_date = _parse_bronze_partition_path(bronze_path)
        definition = DATASET_DEFINITIONS.get((source_name, dataset_id))
        if definition is None:
            raise ValueError(f"unsupported Silver dataset: {source_name}/{dataset_id}")

        raw_rows = READ_TABLE(bronze_path).to_pylist()
        normalized_rows = tuple(
            sorted(
                (
                    self._normalize_row(
                        definition.normalize_row, dataset_id, partition_date, raw_row
                    )
                    for raw_row in raw_rows
                ),
                key=_canonical_row_key,
            )
        )
        output_path = self._output_root / dataset_id / bronze_path.name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table = _table_from_pylist(list(normalized_rows))
        assert_no_forbidden_columns(table.column_names)
        WRITE_TABLE(table, output_path, compression="snappy")
        return output_path

    def normalize_ingest_result(self, result: BronzeIngestResult) -> tuple[Path, ...]:
        manifest = read_manifest(result.manifest_path)
        bronze_root = result.manifest_path.parents[2]
        return tuple(self.normalize_parquet(bronze_root / entry.path) for entry in manifest.entries)

    def normalize_dataset(
        self,
        *,
        bronze_root: Path,
        source_name: str,
        dataset_id: str,
        start: date,
        end: date,
    ) -> tuple[Path, ...]:
        current = start
        written_paths: list[Path] = []
        while current <= end:
            bronze_path = bronze_root / source_name / dataset_id / f"{current.isoformat()}.parquet"
            if bronze_path.is_file():
                written_paths.append(self.normalize_parquet(bronze_path))
            current += timedelta(days=1)
        return tuple(written_paths)

    def _normalize_row(
        self,
        normalize_row: _Normalizer,
        dataset_id: str,
        partition_date: date,
        raw_row: RawRow,
    ) -> SilverRow:
        normalized_row = normalize_row(raw_row)
        as_of_date = normalized_row["as_of_date"]
        if not isinstance(as_of_date, date):
            raise InvalidValueError(dataset_id, "as_of_date", as_of_date)
        if as_of_date != partition_date:
            raise InvalidValueError(dataset_id, "as_of_date", as_of_date.isoformat())
        if not self._calendar.is_trading_day(as_of_date):
            raise NonTradingDayError(dataset_id, as_of_date)
        assert_no_forbidden_columns(normalized_row.keys())
        return normalized_row


def silver_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_bronze_partition_path(path: Path) -> tuple[str, str, date]:
    if len(path.parts) < 3:
        raise ValueError(f"invalid Bronze parquet path: {path}")
    source_name = path.parts[-3]
    dataset_id = path.parts[-2]
    partition_date = date.fromisoformat(path.stem)
    return source_name, dataset_id, partition_date


def _canonical_row_key(row: SilverRow) -> tuple[str, ...]:
    return tuple(f"{column}={row[column]}" for column in sorted(row))


def assert_no_forbidden_columns(columns: Iterable[str]) -> None:
    forbidden = [name for name in columns if name.startswith("target_")]
    if forbidden:
        raise ValueError(f"forbidden columns in Silver output: {forbidden}")


def _normalize_common(raw_row: RawRow, *, dataset_id: str, date_field_name: str) -> SilverRow:
    return {
        "as_of_date": _parse_date(raw_row, date_field_name, dataset_id),
        "source_name": _parse_text(raw_row, "source_name", dataset_id),
        "source_series_id": _parse_text(raw_row, "source_series_id", dataset_id),
        "fetched_at": _parse_text(raw_row, "fetched_at", dataset_id),
    }


def _normalize_kospi_index(raw_row: RawRow) -> SilverRow:
    dataset_id = "kospi_index"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="trade_date")
    row.update(
        {
            "open": _parse_decimal(raw_row, "open_price", dataset_id),
            "high": _parse_decimal(raw_row, "high_price", dataset_id),
            "low": _parse_decimal(raw_row, "low_price", dataset_id),
            "close": _parse_decimal(raw_row, "close_price", dataset_id),
            "volume_shares": _parse_int(raw_row, "volume", dataset_id),
            "turnover_krw": _parse_decimal(raw_row, "turnover", dataset_id),
        }
    )
    return row


def _normalize_investor_flow(raw_row: RawRow) -> SilverRow:
    dataset_id = "investor_flow"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="trade_date")
    row.update(
        {
            "individual_net_buy_krw": _parse_decimal(raw_row, "individual_net_buy", dataset_id),
            "foreign_net_buy_krw": _parse_decimal(raw_row, "foreign_net_buy", dataset_id),
            "institution_net_buy_krw": _parse_decimal(raw_row, "institution_net_buy", dataset_id),
        }
    )
    return row


def _normalize_base_rate(raw_row: RawRow) -> SilverRow:
    dataset_id = "base_rate"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update({"base_rate_pct": _parse_decimal(raw_row, "base_rate", dataset_id)})
    return row


def _normalize_usd_krw(raw_row: RawRow) -> SilverRow:
    dataset_id = "usd_krw"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update({"usd_krw_rate": _parse_decimal(raw_row, "exchange_rate", dataset_id)})
    return row


def _normalize_bond_yield(raw_row: RawRow) -> SilverRow:
    dataset_id = "bond_yield"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update(
        {
            "maturity_code": _parse_text(raw_row, "maturity_code", dataset_id),
            "yield_rate_pct": _parse_decimal(raw_row, "yield_rate", dataset_id),
        }
    )
    return row


def _normalize_per_pbr_percentiles(raw_row: RawRow) -> SilverRow:
    dataset_id = "per_pbr_percentiles"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update(
        {
            "per_percentile_pct": _parse_decimal(raw_row, "per_percentile", dataset_id),
            "pbr_percentile_pct": _parse_decimal(raw_row, "pbr_percentile", dataset_id),
        }
    )
    return row


def _normalize_market_valuation(raw_row: RawRow) -> SilverRow:
    dataset_id = "market_valuation"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="trade_date")
    row.update(
        {
            "market_cap_krw": _parse_decimal(raw_row, "market_capitalization", dataset_id),
            "trailing_per": _parse_decimal(raw_row, "trailing_per", dataset_id),
            "trailing_pbr": _parse_decimal(raw_row, "trailing_pbr", dataset_id),
        }
    )
    return row


def _normalize_macro_indicators(raw_row: RawRow) -> SilverRow:
    dataset_id = "macro_indicators"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update(
        {
            "indicator_name": _parse_text(raw_row, "indicator_name", dataset_id),
            "indicator_value": _parse_decimal(raw_row, "indicator_value", dataset_id),
            "unit": _parse_text(raw_row, "unit", dataset_id),
        }
    )
    return row


def _normalize_sample_dataset(raw_row: RawRow) -> SilverRow:
    dataset_id = "sample_dataset"
    row = _normalize_common(raw_row, dataset_id=dataset_id, date_field_name="value_date")
    row.update(
        {
            "metric_name": _parse_text(raw_row, "metric_name", dataset_id),
            "metric_value": _parse_decimal(raw_row, "metric_value", dataset_id),
        }
    )
    return row


def _require_field(raw_row: RawRow, field_name: str, dataset_id: str) -> object:
    if field_name not in raw_row or raw_row[field_name] is None:
        raise MissingFieldError(dataset_id, field_name)
    return raw_row[field_name]


def _parse_text(raw_row: RawRow, field_name: str, dataset_id: str) -> str:
    value = _require_field(raw_row, field_name, dataset_id)
    text = str(value)
    if text == "":
        raise InvalidValueError(dataset_id, field_name, value)
    return text


def _parse_date(raw_row: RawRow, field_name: str, dataset_id: str) -> date:
    value = _require_field(raw_row, field_name, dataset_id)
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise InvalidValueError(dataset_id, field_name, value) from exc


def _parse_decimal(raw_row: RawRow, field_name: str, dataset_id: str) -> Decimal:
    value = _require_field(raw_row, field_name, dataset_id)
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidValueError(dataset_id, field_name, value) from exc


def _parse_int(raw_row: RawRow, field_name: str, dataset_id: str) -> int:
    value = _require_field(raw_row, field_name, dataset_id)
    try:
        return int(str(value))
    except ValueError as exc:
        raise InvalidValueError(dataset_id, field_name, value) from exc


DATASET_DEFINITIONS: dict[tuple[str, str], DatasetDefinition] = {
    ("krx", "kospi_index"): DatasetDefinition(normalize_row=_normalize_kospi_index),
    ("krx", "investor_flow"): DatasetDefinition(normalize_row=_normalize_investor_flow),
    ("krx", "market_valuation"): DatasetDefinition(normalize_row=_normalize_market_valuation),
    ("ecos", "base_rate"): DatasetDefinition(normalize_row=_normalize_base_rate),
    ("ecos", "usd_krw"): DatasetDefinition(normalize_row=_normalize_usd_krw),
    ("ecos", "bond_yield"): DatasetDefinition(normalize_row=_normalize_bond_yield),
    ("kosis", "per_pbr_percentiles"): DatasetDefinition(
        normalize_row=_normalize_per_pbr_percentiles
    ),
    ("kosis", "macro_indicators"): DatasetDefinition(normalize_row=_normalize_macro_indicators),
    ("data_portal", "sample_dataset"): DatasetDefinition(normalize_row=_normalize_sample_dataset),
}


__all__ = [
    "DATASET_DEFINITIONS",
    "DatasetDefinition",
    "InvalidValueError",
    "MissingFieldError",
    "NonTradingDayError",
    "SilverNormalizer",
    "TradingCalendar",
    "assert_no_forbidden_columns",
    "silver_sha256",
]
