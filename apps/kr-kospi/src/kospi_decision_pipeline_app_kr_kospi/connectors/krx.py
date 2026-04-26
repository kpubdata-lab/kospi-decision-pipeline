from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import importlib
from typing import Protocol, cast, final, runtime_checkable

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


class PykrxStockApi(Protocol):
    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> object: ...

    def get_market_trading_value_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        etf: bool = False,
        etn: bool = False,
        elw: bool = False,
        on: str = "순매수",
        detail: bool = False,
        freq: str = "d",
    ) -> object: ...

    def get_index_fundamental_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        prev: bool = True,
    ) -> object: ...


class _FrameIndex(Protocol):
    def tolist(self) -> list[object]: ...


class _FrameAtAccessor(Protocol):
    def __getitem__(self, key: tuple[object, str]) -> object: ...


class FrameLike(Protocol):
    @property
    def empty(self) -> bool: ...

    @property
    def index(self) -> _FrameIndex: ...

    @property
    def at(self) -> _FrameAtAccessor: ...

    def sort_index(self) -> "FrameLike": ...


class Sleep(Protocol):
    def __call__(self, seconds: float, /) -> object: ...


class Clock(Protocol):
    def __call__(self) -> datetime: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _default_sleep(seconds: float) -> None:
    from time import sleep

    sleep(seconds)


def _load_default_stock_api() -> PykrxStockApi:
    return cast(PykrxStockApi, importlib.import_module("pykrx.stock"))


def _format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _parse_decimal(value: object) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value from pykrx: {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"non-finite decimal value from pykrx: {value!r}")
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
    raise ValueError(f"unsupported row date value from pykrx: {value!r}")


def _as_frame(frame: object) -> FrameLike:
    return cast(FrameLike, frame)


def _sorted_index_values(frame: FrameLike) -> tuple[object, ...]:
    return tuple(frame.index.tolist())


def _frame_value(frame: FrameLike, index_value: object, column_name: str) -> object:
    return frame.at[index_value, column_name]


def _chunk_date_ranges(start: date, end: date, *, chunk_days: int) -> tuple[tuple[date, date], ...]:
    chunks: list[tuple[date, date]] = []
    current_start = start
    while current_start <= end:
        current_end = min(current_start + timedelta(days=chunk_days), end)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    return tuple(chunks)


@final
class PykrxKrxConnector:
    SOURCE_NAME = "krx"
    KOSPI_INDEX_TICKER = "1001"
    MAX_CHUNK_DAYS = 730

    _stock_api: PykrxStockApi | None
    _clock: Clock
    _sleep: Sleep

    def __init__(
        self,
        *,
        stock_api: PykrxStockApi | None = None,
        clock: Clock = _utc_now,
        sleep: Sleep = _default_sleep,
    ) -> None:
        self._stock_api = stock_api
        self._clock = clock
        self._sleep = sleep

    @property
    def stock_api(self) -> PykrxStockApi:
        if self._stock_api is None:
            self._stock_api = _load_default_stock_api()
        return self._stock_api

    def fetch_kospi_index(self, start: date, end: date) -> tuple[KospiIndexRow, ...]:
        metadata = self._metadata(dataset_name="kospi_index")
        rows: list[KospiIndexRow] = []
        request = _ChunkedPykrxRequester(
            sleep=self._sleep,
            should_throttle=(end - start).days > self.MAX_CHUNK_DAYS,
        )
        for chunk_start, chunk_end in _chunk_date_ranges(
            start, end, chunk_days=self.MAX_CHUNK_DAYS
        ):
            frame = _as_frame(
                request.call(
                    self.stock_api.get_index_ohlcv_by_date,
                    _format_date(chunk_start),
                    _format_date(chunk_end),
                    self.KOSPI_INDEX_TICKER,
                    freq="d",
                    name_display=False,
                )
            )
            rows.extend(self._build_kospi_index_rows(frame, metadata))
        return tuple(sorted(rows, key=lambda row: row.trade_date))

    def fetch_investor_flow(self, start: date, end: date) -> tuple[InvestorFlowRow, ...]:
        metadata = self._metadata(dataset_name="investor_flow")
        rows: list[InvestorFlowRow] = []
        request = _ChunkedPykrxRequester(
            sleep=self._sleep,
            should_throttle=(end - start).days > self.MAX_CHUNK_DAYS,
        )
        for chunk_start, chunk_end in _chunk_date_ranges(
            start, end, chunk_days=self.MAX_CHUNK_DAYS
        ):
            frame = _as_frame(
                request.call(
                    self.stock_api.get_market_trading_value_by_date,
                    _format_date(chunk_start),
                    _format_date(chunk_end),
                    "KOSPI",
                    etf=False,
                    etn=False,
                    elw=False,
                    on="순매수",
                    detail=False,
                    freq="d",
                )
            )
            rows.extend(self._build_investor_flow_rows(frame, metadata))
        return tuple(sorted(rows, key=lambda row: row.trade_date))

    def fetch_market_valuation(self, start: date, end: date) -> tuple[MarketValuationRow, ...]:
        metadata = self._metadata(dataset_name="market_valuation")
        rows: list[MarketValuationRow] = []
        request = _ChunkedPykrxRequester(
            sleep=self._sleep,
            should_throttle=(end - start).days > self.MAX_CHUNK_DAYS,
        )
        for chunk_start, chunk_end in _chunk_date_ranges(
            start, end, chunk_days=self.MAX_CHUNK_DAYS
        ):
            ohlcv_frame = _as_frame(
                request.call(
                    self.stock_api.get_index_ohlcv_by_date,
                    _format_date(chunk_start),
                    _format_date(chunk_end),
                    self.KOSPI_INDEX_TICKER,
                    freq="d",
                    name_display=False,
                )
            )
            fundamental_frame = _as_frame(
                request.call(
                    self.stock_api.get_index_fundamental_by_date,
                    _format_date(chunk_start),
                    _format_date(chunk_end),
                    self.KOSPI_INDEX_TICKER,
                    prev=True,
                )
            )
            rows.extend(self._build_market_valuation_rows(ohlcv_frame, fundamental_frame, metadata))
        return tuple(sorted(rows, key=lambda row: row.trade_date))

    def _metadata(self, *, dataset_name: str) -> SourceMetadata:
        fetched_at_utc = self._clock().astimezone(timezone.utc).replace(microsecond=0).isoformat()
        connector_type = type(self)

        return SourceMetadata(
            source_name=self.SOURCE_NAME,
            dataset_name=dataset_name,
            fetched_at_utc=fetched_at_utc,
            connector_id=f"{connector_type.__module__}.{connector_type.__qualname__}",
        )

    def _build_kospi_index_rows(
        self, frame: FrameLike, metadata: SourceMetadata
    ) -> tuple[KospiIndexRow, ...]:
        if frame.empty:
            return ()
        sorted_frame = frame.sort_index()
        return tuple(
            KospiIndexRow(
                metadata=metadata,
                trade_date=_row_date(index_value),
                open_price=_parse_decimal(_frame_value(sorted_frame, index_value, "시가")),
                high_price=_parse_decimal(_frame_value(sorted_frame, index_value, "고가")),
                low_price=_parse_decimal(_frame_value(sorted_frame, index_value, "저가")),
                close_price=_parse_decimal(_frame_value(sorted_frame, index_value, "종가")),
                volume=_parse_int(_frame_value(sorted_frame, index_value, "거래량")),
                turnover=_parse_decimal(_frame_value(sorted_frame, index_value, "거래대금")),
            )
            for index_value in _sorted_index_values(sorted_frame)
        )

    def _build_investor_flow_rows(
        self, frame: FrameLike, metadata: SourceMetadata
    ) -> tuple[InvestorFlowRow, ...]:
        if frame.empty:
            return ()
        sorted_frame = frame.sort_index()
        return tuple(
            InvestorFlowRow(
                metadata=metadata,
                trade_date=_row_date(index_value),
                individual_net_buy=_parse_decimal(_frame_value(sorted_frame, index_value, "개인")),
                foreign_net_buy=_parse_decimal(
                    _frame_value(sorted_frame, index_value, "외국인합계")
                ),
                institution_net_buy=_parse_decimal(
                    _frame_value(sorted_frame, index_value, "기관합계")
                ),
            )
            for index_value in _sorted_index_values(sorted_frame)
        )

    def _build_market_valuation_rows(
        self,
        ohlcv_frame: FrameLike,
        fundamental_frame: FrameLike,
        metadata: SourceMetadata,
    ) -> tuple[MarketValuationRow, ...]:
        if ohlcv_frame.empty or fundamental_frame.empty:
            return ()
        sorted_ohlcv = ohlcv_frame.sort_index()
        sorted_fundamental = fundamental_frame.sort_index()
        fundamental_index = frozenset(_sorted_index_values(sorted_fundamental))
        joined_index = tuple(
            index_value
            for index_value in _sorted_index_values(sorted_ohlcv)
            if index_value in fundamental_index
        )
        return tuple(
            MarketValuationRow(
                metadata=metadata,
                trade_date=_row_date(index_value),
                market_capitalization=_parse_decimal(
                    _frame_value(sorted_ohlcv, index_value, "상장시가총액")
                ),
                trailing_per=_parse_decimal(_frame_value(sorted_fundamental, index_value, "PER")),
                trailing_pbr=_parse_decimal(_frame_value(sorted_fundamental, index_value, "PBR")),
            )
            for index_value in joined_index
        )


class _PykrxOperation(Protocol):
    def __call__(self, /, *args: object, **kwargs: object) -> object: ...


@dataclass(slots=True)
class _ChunkedPykrxRequester:
    sleep: Sleep
    should_throttle: bool
    _call_count: int = 0

    def call(self, operation: object, /, *args: object, **kwargs: object) -> object:
        if self.should_throttle and self._call_count > 0:
            _ = self.sleep(1.0)
        self._call_count += 1
        fetch = cast(_PykrxOperation, operation)
        return fetch(*args, **kwargs)
