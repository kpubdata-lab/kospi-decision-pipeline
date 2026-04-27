from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast, final, runtime_checkable

from kpubdata import Client

from .base import ConnectorRowBase, SourceMetadata


@dataclass(frozen=True, slots=True)
class KospiIndexRow(ConnectorRowBase):
    trade_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    turnover: Decimal


@dataclass(frozen=True, slots=True)
class InvestorFlowRow(ConnectorRowBase):
    trade_date: date
    individual_net_buy: Decimal
    foreign_net_buy: Decimal
    institution_net_buy: Decimal


@dataclass(frozen=True, slots=True)
class MarketValuationRow(ConnectorRowBase):
    trade_date: date
    market_capitalization: Decimal
    trailing_per: Decimal
    trailing_pbr: Decimal


@runtime_checkable
class KrxConnector(Protocol):
    def fetch_kospi_index(self, start: date, end: date) -> tuple[KospiIndexRow, ...]: ...

    def fetch_investor_flow(self, start: date, end: date) -> tuple[InvestorFlowRow, ...]: ...

    def fetch_market_valuation(self, start: date, end: date) -> tuple[MarketValuationRow, ...]: ...


_KOSPI_INDEX_DATASET_ID = "krx.kospi_index"
_INVESTOR_FLOW_DATASET_ID = "krx.investor_flow"
_MARKET_VALUATION_DATASET_ID = "krx.market_valuation"
_INDIVIDUAL_INVESTOR_TYPE = "개인"
_FOREIGN_INVESTOR_TYPE = "외국인"
_INSTITUTION_INVESTOR_TYPE = "기관"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value from kpubdata: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"non-finite decimal value from kpubdata: {value!r}")
    return parsed


def _parse_int(value: object) -> int:
    return int(str(value))


def _row_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"unsupported row date value from kpubdata: {value!r}")


def _require_record_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        raise ValueError("KRX record batch payload must be a sequence")
    raw_payload = cast(Sequence[object], payload)
    rows: list[Mapping[str, object]] = []
    for raw_row in raw_payload:
        if not isinstance(raw_row, Mapping):
            raise ValueError("KRX record payload must be an object")
        rows.append(cast(Mapping[str, object], raw_row))
    return tuple(rows)


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing KRX string field: {key}")
    return value


def _require_value(mapping: Mapping[str, object], key: str) -> object:
    if key not in mapping:
        raise ValueError(f"missing KRX field: {key}")
    return mapping[key]


@final
class PykrxKrxConnector:
    SOURCE_NAME = "krx"

    _client: Client
    _clock: Callable[[], datetime]

    def __init__(self, *, client: Client, clock: Callable[[], datetime] = _utc_now) -> None:
        self._client = client
        self._clock = clock

    def fetch_kospi_index(self, start: date, end: date) -> tuple[KospiIndexRow, ...]:
        return parse_kospi_index_rows(
            payload=self._query_dataset(_KOSPI_INDEX_DATASET_ID, start, end),
            fetched_at_utc=self._fetched_at_utc(),
            connector_id=self._connector_id(),
        )

    def fetch_investor_flow(self, start: date, end: date) -> tuple[InvestorFlowRow, ...]:
        return parse_investor_flow_rows(
            payload=self._query_dataset(_INVESTOR_FLOW_DATASET_ID, start, end),
            fetched_at_utc=self._fetched_at_utc(),
            connector_id=self._connector_id(),
        )

    def fetch_market_valuation(self, start: date, end: date) -> tuple[MarketValuationRow, ...]:
        return parse_market_valuation_rows(
            payload=self._query_dataset(_MARKET_VALUATION_DATASET_ID, start, end),
            market_caps_payload=self._query_dataset(_KOSPI_INDEX_DATASET_ID, start, end),
            fetched_at_utc=self._fetched_at_utc(),
            connector_id=self._connector_id(),
        )

    def _query_dataset(
        self,
        dataset_id: str,
        start: date,
        end: date,
    ) -> tuple[Mapping[str, object], ...]:
        batch = self._client.dataset(dataset_id).list(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        return _require_record_rows(batch.items)

    def _connector_id(self) -> str:
        connector_type = type(self)
        return f"{connector_type.__module__}.{connector_type.__qualname__}"

    def _fetched_at_utc(self) -> str:
        return self._clock().astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_kospi_index_rows(
    *,
    payload: object,
    fetched_at_utc: str,
    connector_id: str,
) -> tuple[KospiIndexRow, ...]:
    metadata = _source_metadata("kospi_index", fetched_at_utc, connector_id)
    rows = _require_record_rows(payload)
    return tuple(
        sorted(
            (
                KospiIndexRow(
                    metadata=metadata,
                    trade_date=_row_date(_require_value(raw_row, "date")),
                    open_price=_parse_decimal(_require_value(raw_row, "open")),
                    high_price=_parse_decimal(_require_value(raw_row, "high")),
                    low_price=_parse_decimal(_require_value(raw_row, "low")),
                    close_price=_parse_decimal(_require_value(raw_row, "close")),
                    volume=_parse_int(_require_value(raw_row, "volume")),
                    turnover=_parse_decimal(_require_value(raw_row, "trading_value")),
                )
                for raw_row in rows
            ),
            key=lambda row: row.trade_date,
        )
    )


def parse_investor_flow_rows(
    *,
    payload: object,
    fetched_at_utc: str,
    connector_id: str,
) -> tuple[InvestorFlowRow, ...]:
    metadata = _source_metadata("investor_flow", fetched_at_utc, connector_id)
    aggregated: dict[date, dict[str, Decimal]] = {}
    for raw_row in _require_record_rows(payload):
        trade_date = _row_date(_require_value(raw_row, "date"))
        investor_type = _require_string(raw_row, "investor_type")
        totals = aggregated.setdefault(trade_date, {})
        current_total = totals.get(investor_type, Decimal("0"))
        totals[investor_type] = current_total + _parse_decimal(_require_value(raw_row, "net_value"))
    return tuple(
        InvestorFlowRow(
            metadata=metadata,
            trade_date=trade_date,
            individual_net_buy=totals.get(_INDIVIDUAL_INVESTOR_TYPE, Decimal("0")),
            foreign_net_buy=totals.get(_FOREIGN_INVESTOR_TYPE, Decimal("0")),
            institution_net_buy=totals.get(_INSTITUTION_INVESTOR_TYPE, Decimal("0")),
        )
        for trade_date, totals in sorted(aggregated.items())
    )


def parse_market_valuation_rows(
    *,
    payload: object,
    market_caps_payload: object,
    fetched_at_utc: str,
    connector_id: str,
) -> tuple[MarketValuationRow, ...]:
    metadata = _source_metadata("market_valuation", fetched_at_utc, connector_id)
    market_caps = {
        _row_date(_require_value(raw_row, "date")): _parse_decimal(
            _require_value(raw_row, "market_cap")
        )
        for raw_row in _require_record_rows(market_caps_payload)
    }
    rows: list[MarketValuationRow] = []
    for raw_row in _require_record_rows(payload):
        trade_date = _row_date(_require_value(raw_row, "date"))
        market_capitalization = market_caps.get(trade_date)
        if market_capitalization is None:
            continue
        rows.append(
            MarketValuationRow(
                metadata=metadata,
                trade_date=trade_date,
                market_capitalization=market_capitalization,
                trailing_per=_parse_decimal(_require_value(raw_row, "per")),
                trailing_pbr=_parse_decimal(_require_value(raw_row, "pbr")),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.trade_date))


def _source_metadata(dataset_name: str, fetched_at_utc: str, connector_id: str) -> SourceMetadata:
    return SourceMetadata(
        source_name="krx",
        dataset_name=dataset_name,
        fetched_at_utc=fetched_at_utc,
        connector_id=connector_id,
    )
