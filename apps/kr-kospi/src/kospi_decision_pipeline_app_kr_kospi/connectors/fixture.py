from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Callable, TypeVar, cast, final

from .base import SourceMetadata
from .data_portal import DataPortalSampleRow
from .ecos import EcosBaseRateRow, EcosBondYieldRow, EcosUsdKrwRow
from .kosis import KosisMacroIndicatorRow, PerPbrPercentileRow
from .krx import InvestorFlowRow, KospiIndexRow, MarketValuationRow


@dataclass(frozen=True, slots=True)
class _FixturePayload:
    metadata: SourceMetadata
    rows: tuple[dict[str, object], ...]


RowT = TypeVar("RowT")


@final
class _FixtureLoader:
    _fixtures_root: Path

    def __init__(self, fixtures_root: Path) -> None:
        self._fixtures_root = fixtures_root

    def load(self, source_name: str, dataset_name: str, connector_id: str) -> _FixturePayload:
        fixture_path = self._fixtures_root / source_name / f"{dataset_name}.json"
        payload = cast(dict[str, object], json.loads(fixture_path.read_text(encoding="utf-8")))
        metadata = SourceMetadata(
            source_name=str(payload["source_name"]),
            dataset_name=str(payload["source_series_id"]),
            fetched_at_utc=datetime.fromisoformat(str(payload["fetched_at"])).isoformat(),
            connector_id=connector_id,
        )
        raw_rows = cast(list[dict[str, object]], payload["rows"])
        return _FixturePayload(metadata=metadata, rows=tuple(raw_rows))


def _parse_date(value: object) -> date:
    return date.fromisoformat(str(value))


def _parse_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _parse_int(value: object) -> int:
    return int(str(value))


def _filter_by_date_range(
    rows: tuple[RowT, ...],
    date_getter: Callable[[RowT], date],
    start: date,
    end: date,
) -> tuple[RowT, ...]:
    return tuple(row for row in rows if start <= date_getter(row) <= end)


@final
class FixtureKrxConnector:
    _loader: _FixtureLoader

    def __init__(self, fixtures_root: Path) -> None:
        self._loader = _FixtureLoader(fixtures_root)

    def fetch_kospi_index(self, start: date, end: date) -> tuple[KospiIndexRow, ...]:
        payload = self._loader.load("krx", "kospi_index", _connector_id(self))
        rows = tuple(
            KospiIndexRow(
                metadata=payload.metadata,
                trade_date=_parse_date(row["trade_date"]),
                open_price=_parse_decimal(row["open_price"]),
                high_price=_parse_decimal(row["high_price"]),
                low_price=_parse_decimal(row["low_price"]),
                close_price=_parse_decimal(row["close_price"]),
                volume=_parse_int(row["volume"]),
                turnover=_parse_decimal(row["turnover"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.trade_date, start, end)

    def fetch_investor_flow(self, start: date, end: date) -> tuple[InvestorFlowRow, ...]:
        payload = self._loader.load("krx", "investor_flow", _connector_id(self))
        rows = tuple(
            InvestorFlowRow(
                metadata=payload.metadata,
                trade_date=_parse_date(row["trade_date"]),
                individual_net_buy=_parse_decimal(row["individual_net_buy"]),
                foreign_net_buy=_parse_decimal(row["foreign_net_buy"]),
                institution_net_buy=_parse_decimal(row["institution_net_buy"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.trade_date, start, end)

    def fetch_market_valuation(self, start: date, end: date) -> tuple[MarketValuationRow, ...]:
        payload = self._loader.load("krx", "market_valuation", _connector_id(self))
        rows = tuple(
            MarketValuationRow(
                metadata=payload.metadata,
                trade_date=_parse_date(row["trade_date"]),
                market_capitalization=_parse_decimal(row["market_capitalization"]),
                trailing_per=_parse_decimal(row["trailing_per"]),
                trailing_pbr=_parse_decimal(row["trailing_pbr"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.trade_date, start, end)


@final
class FixtureEcosConnector:
    _loader: _FixtureLoader

    def __init__(self, fixtures_root: Path) -> None:
        self._loader = _FixtureLoader(fixtures_root)

    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]:
        payload = self._loader.load("ecos", "base_rate", _connector_id(self))
        rows = tuple(
            EcosBaseRateRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                base_rate=_parse_decimal(row["base_rate"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)

    def fetch_usd_krw_series(self, start: date, end: date) -> tuple[EcosUsdKrwRow, ...]:
        payload = self._loader.load("ecos", "usd_krw", _connector_id(self))
        rows = tuple(
            EcosUsdKrwRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                exchange_rate=_parse_decimal(row["exchange_rate"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)

    def fetch_bond_yield_series(self, start: date, end: date) -> tuple[EcosBondYieldRow, ...]:
        payload = self._loader.load("ecos", "bond_yield", _connector_id(self))
        rows = tuple(
            EcosBondYieldRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                maturity_code=str(row["maturity_code"]),
                yield_rate=_parse_decimal(row["yield_rate"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)


@final
class FixtureKosisConnector:
    _loader: _FixtureLoader

    def __init__(self, fixtures_root: Path) -> None:
        self._loader = _FixtureLoader(fixtures_root)

    def fetch_per_pbr_percentiles(self, start: date, end: date) -> tuple[PerPbrPercentileRow, ...]:
        payload = self._loader.load("kosis", "per_pbr_percentiles", _connector_id(self))
        rows = tuple(
            PerPbrPercentileRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                per_percentile=_parse_decimal(row["per_percentile"]),
                pbr_percentile=_parse_decimal(row["pbr_percentile"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)

    def fetch_macro_indicators(self, start: date, end: date) -> tuple[KosisMacroIndicatorRow, ...]:
        payload = self._loader.load("kosis", "macro_indicators", _connector_id(self))
        rows = tuple(
            KosisMacroIndicatorRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                indicator_name=str(row["indicator_name"]),
                indicator_value=_parse_decimal(row["indicator_value"]),
                unit=str(row["unit"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)


@final
class FixtureDataPortalConnector:
    _loader: _FixtureLoader

    def __init__(self, fixtures_root: Path) -> None:
        self._loader = _FixtureLoader(fixtures_root)

    def fetch_sample_dataset(self, start: date, end: date) -> tuple[DataPortalSampleRow, ...]:
        payload = self._loader.load("data_portal", "sample_dataset", _connector_id(self))
        rows = tuple(
            DataPortalSampleRow(
                metadata=payload.metadata,
                value_date=_parse_date(row["value_date"]),
                metric_name=str(row["metric_name"]),
                metric_value=_parse_decimal(row["metric_value"]),
            )
            for row in payload.rows
        )
        return _filter_by_date_range(rows, lambda row: row.value_date, start, end)


def _connector_id(connector: object) -> str:
    connector_type = type(connector)
    return f"{connector_type.__module__}.{connector_type.__qualname__}"
