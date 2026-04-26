from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import cast
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    MarketValuationRow,
    PykrxKrxConnector,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "krx"


def _parse_pykrx_date(value: object) -> date:
    return datetime.strptime(str(value), "%Y%m%d").date()


class FakeFrameIndex:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def tolist(self) -> list[object]:
        return list(self._values)


class FakeFrameAtAccessor:
    def __init__(self, rows: dict[object, dict[str, object]]) -> None:
        self._rows = rows

    def __getitem__(self, key: tuple[object, str]) -> object:
        index_value, column_name = key
        return self._rows[index_value][column_name]


class FakeDataFrame:
    def __init__(self, rows: dict[object, dict[str, object]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    @property
    def index(self) -> FakeFrameIndex:
        return FakeFrameIndex(tuple(self._rows))

    @property
    def at(self) -> FakeFrameAtAccessor:
        return FakeFrameAtAccessor(self._rows)

    def sort_index(self) -> FakeDataFrame:
        return FakeDataFrame(dict(sorted(self._rows.items(), key=lambda item: str(item[0]))))


def _load_frame_fixture(name: str) -> FakeDataFrame:
    payload = cast(
        dict[str, object], json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    )
    raw_rows = cast(list[dict[str, object]], payload["rows"])
    rows: dict[object, dict[str, object]] = {}
    for raw_row in raw_rows:
        rows[datetime.fromisoformat(str(raw_row["index"]))] = cast(
            dict[str, object], raw_row["values"]
        )
    return FakeDataFrame(rows)


def _load_market_valuation_frames() -> tuple[FakeDataFrame, FakeDataFrame]:
    payload = cast(
        dict[str, object],
        json.loads((FIXTURES_ROOT / "market_valuation_frames.json").read_text(encoding="utf-8")),
    )

    def _as_frame(frame_payload: object) -> FakeDataFrame:
        mapping = cast(dict[str, object], frame_payload)
        raw_rows = cast(list[dict[str, object]], mapping["rows"])
        rows: dict[object, dict[str, object]] = {}
        for raw_row in raw_rows:
            rows[datetime.fromisoformat(str(raw_row["index"]))] = cast(
                dict[str, object], raw_row["values"]
            )
        return FakeDataFrame(rows)

    return (_as_frame(payload["ohlcv"]), _as_frame(payload["fundamental"]))


class FakePykrxStockApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self._kospi_index_frame = _load_frame_fixture("kospi_index_frame.json")
        self._investor_flow_frame = _load_frame_fixture("investor_flow_frame.json")
        self._market_valuation_ohlcv_frame, self._market_valuation_fundamental_frame = (
            _load_market_valuation_frames()
        )

    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> FakeDataFrame:
        self.calls.append(
            (
                "get_index_ohlcv_by_date",
                (fromdate, todate, ticker),
                {"freq": freq, "name_display": name_display},
            )
        )
        if fromdate == "20240106":
            return FakeDataFrame({})
        return (
            self._market_valuation_ohlcv_frame
            if fromdate == "20240102" and todate == "20240103"
            else self._kospi_index_frame
        )

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
    ) -> FakeDataFrame:
        self.calls.append(
            (
                "get_market_trading_value_by_date",
                (fromdate, todate, ticker),
                {
                    "etf": etf,
                    "etn": etn,
                    "elw": elw,
                    "on": on,
                    "detail": detail,
                    "freq": freq,
                },
            )
        )
        if fromdate == "20240106":
            return FakeDataFrame({})
        return self._investor_flow_frame

    def get_index_fundamental_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        prev: bool = True,
    ) -> FakeDataFrame:
        self.calls.append(
            (
                "get_index_fundamental_by_date",
                (fromdate, todate, ticker),
                {"prev": prev},
            )
        )
        if fromdate == "20240106":
            return FakeDataFrame({})
        return self._market_valuation_fundamental_frame


class InvalidDecimalStockApi(FakePykrxStockApi):
    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> FakeDataFrame:
        return FakeDataFrame(
            {
                datetime(2024, 1, 2): {
                    "시가": "bad-decimal",
                    "고가": 1,
                    "저가": 1,
                    "종가": 1,
                    "거래량": 1,
                    "거래대금": 1,
                    "상장시가총액": 1,
                }
            }
        )


class NonFiniteDecimalStockApi(FakePykrxStockApi):
    def get_index_fundamental_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        prev: bool = True,
    ) -> FakeDataFrame:
        return FakeDataFrame({datetime(2024, 1, 2): {"PER": "NaN", "PBR": 0.93}})


class UnsupportedDateStockApi(FakePykrxStockApi):
    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> FakeDataFrame:
        return FakeDataFrame(
            {
                cast(datetime, object()): {
                    "시가": 1,
                    "고가": 1,
                    "저가": 1,
                    "종가": 1,
                    "거래량": 1,
                    "거래대금": 1,
                    "상장시가총액": 1,
                }
            }
        )


class NativeDateStockApi(FakePykrxStockApi):
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
    ) -> FakeDataFrame:
        return FakeDataFrame(
            {
                datetime(2024, 1, 2).date(): {
                    "개인": Decimal("1"),
                    "외국인합계": Decimal("2"),
                    "기관합계": Decimal("3"),
                }
            }
        )


class StringDateStockApi(FakePykrxStockApi):
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
    ) -> FakeDataFrame:
        return FakeDataFrame(
            {
                "2024-01-02 00:00:00": {
                    "개인": Decimal("1"),
                    "외국인합계": Decimal("2"),
                    "기관합계": Decimal("3"),
                }
            }
        )


def test_pykrx_krx_connector_normalizes_dataframes_into_typed_rows() -> None:
    connector = PykrxKrxConnector(
        stock_api=FakePykrxStockApi(),
        clock=lambda: datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc),
    )

    kospi_rows = connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 3))
    investor_rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 3))
    valuation_rows = connector.fetch_market_valuation(date(2024, 1, 2), date(2024, 1, 3))

    assert kospi_rows == (
        KospiIndexRow(
            metadata=kospi_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            open_price=Decimal("2640.5"),
            high_price=Decimal("2655.0"),
            low_price=Decimal("2621.0"),
            close_price=Decimal("2651.8"),
            volume=470000000,
            turnover=Decimal("9200000000000"),
        ),
        KospiIndexRow(
            metadata=kospi_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            open_price=Decimal("2660.0"),
            high_price=Decimal("2672.1"),
            low_price=Decimal("2631.5"),
            close_price=Decimal("2645.2"),
            volume=460000000,
            turnover=Decimal("9100000000000"),
        ),
    )
    assert investor_rows == (
        InvestorFlowRow(
            metadata=investor_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            individual_net_buy=Decimal("100000000000"),
            foreign_net_buy=Decimal("-120000000000"),
            institution_net_buy=Decimal("20000000000"),
        ),
        InvestorFlowRow(
            metadata=investor_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            individual_net_buy=Decimal("-200000000000"),
            foreign_net_buy=Decimal("150000000000"),
            institution_net_buy=Decimal("50000000000"),
        ),
    )
    assert valuation_rows == (
        MarketValuationRow(
            metadata=valuation_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            market_capitalization=Decimal("2110000000000000"),
            trailing_per=Decimal("12.2"),
            trailing_pbr=Decimal("0.93"),
        ),
        MarketValuationRow(
            metadata=valuation_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            market_capitalization=Decimal("2100000000000000"),
            trailing_per=Decimal("12.5"),
            trailing_pbr=Decimal("0.95"),
        ),
    )
    assert kospi_rows[0].metadata.source_name == "krx"
    assert kospi_rows[0].metadata.dataset_name == "kospi_index"
    assert kospi_rows[0].metadata.connector_id.endswith("PykrxKrxConnector")
    assert kospi_rows[0].metadata.fetched_at_utc == "2024-01-10T09:00:00+00:00"
    assert investor_rows[0].metadata.dataset_name == "investor_flow"
    assert valuation_rows[0].metadata.dataset_name == "market_valuation"


def test_pykrx_krx_connector_returns_empty_rows_for_empty_window() -> None:
    connector = PykrxKrxConnector(stock_api=FakePykrxStockApi())

    assert connector.fetch_kospi_index(date(2024, 1, 6), date(2024, 1, 7)) == ()
    assert connector.fetch_investor_flow(date(2024, 1, 6), date(2024, 1, 7)) == ()
    assert connector.fetch_market_valuation(date(2024, 1, 6), date(2024, 1, 7)) == ()


def test_pykrx_krx_connector_sleeps_between_chunked_pykrx_calls() -> None:
    stock_api = FakePykrxStockApi()
    sleep_calls: list[float] = []
    connector = PykrxKrxConnector(stock_api=stock_api, sleep=sleep_calls.append)

    _ = connector.fetch_kospi_index(date(2020, 1, 1), date(2024, 12, 31))

    assert [call[0] for call in stock_api.calls] == [
        "get_index_ohlcv_by_date",
        "get_index_ohlcv_by_date",
        "get_index_ohlcv_by_date",
    ]
    chunk_ranges = [
        (_parse_pykrx_date(call[1][0]), _parse_pykrx_date(call[1][1])) for call in stock_api.calls
    ]
    assert chunk_ranges[0][0] == date(2020, 1, 1)
    assert chunk_ranges[-1][1] == date(2024, 12, 31)
    assert all((chunk_end - chunk_start).days <= 730 for chunk_start, chunk_end in chunk_ranges)
    assert sleep_calls == [1.0, 1.0]


def test_pykrx_krx_connector_lazy_loads_pykrx_and_uses_default_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stock_api = FakePykrxStockApi()
    sleep_calls: list[float] = []

    def fake_import_module(name: str) -> FakePykrxStockApi:
        assert name == "pykrx.stock"
        return stock_api

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.krx.importlib.import_module",
        fake_import_module,
    )
    monkeypatch.setattr("time.sleep", fake_sleep)

    connector = PykrxKrxConnector()

    _ = connector.fetch_kospi_index(date(2020, 1, 1), date(2024, 12, 31))

    assert sleep_calls == [1.0, 1.0]
    assert len(stock_api.calls) == 3


def test_pykrx_krx_connector_rejects_invalid_decimal_values() -> None:
    connector = PykrxKrxConnector(stock_api=InvalidDecimalStockApi())

    with pytest.raises(ValueError, match="invalid decimal value"):
        connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 2))


def test_pykrx_krx_connector_rejects_non_finite_decimal_values() -> None:
    connector = PykrxKrxConnector(stock_api=NonFiniteDecimalStockApi())

    with pytest.raises(ValueError, match="non-finite decimal value"):
        connector.fetch_market_valuation(date(2024, 1, 2), date(2024, 1, 2))


def test_pykrx_krx_connector_rejects_unsupported_row_dates() -> None:
    connector = PykrxKrxConnector(stock_api=UnsupportedDateStockApi())

    with pytest.raises(ValueError, match="unsupported row date value"):
        connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 2))


def test_pykrx_krx_connector_accepts_native_date_index_values() -> None:
    connector = PykrxKrxConnector(stock_api=NativeDateStockApi())

    rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 2))

    assert rows[0].trade_date == date(2024, 1, 2)


def test_pykrx_krx_connector_accepts_string_date_index_values() -> None:
    connector = PykrxKrxConnector(stock_api=StringDateStockApi())

    rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 2))

    assert rows[0].trade_date == date(2024, 1, 2)


def test_pykrx_krx_connector_frame_fixtures_capture_expected_adapter_shapes() -> None:
    kospi_frame = _load_frame_fixture("kospi_index_frame.json")
    investor_frame = _load_frame_fixture("investor_flow_frame.json")
    valuation_ohlcv_frame, valuation_fundamental_frame = _load_market_valuation_frames()

    assert kospi_frame.index.tolist() == [datetime(2024, 1, 3), datetime(2024, 1, 2)]
    assert kospi_frame.at[datetime(2024, 1, 3), "시가"] == "2660.0"
    assert investor_frame.at[datetime(2024, 1, 2), "외국인합계"] == "-120000000000"
    assert valuation_ohlcv_frame.at[datetime(2024, 1, 2), "상장시가총액"] == "2110000000000000"
    assert valuation_fundamental_frame.at[datetime(2024, 1, 3), "PER"] == "12.5"


def test_pykrx_krx_connector_sorts_fixture_backed_rows_deterministically() -> None:
    connector = PykrxKrxConnector(stock_api=FakePykrxStockApi())

    kospi_rows = connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 3))
    investor_rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 3))
    valuation_rows = connector.fetch_market_valuation(date(2024, 1, 2), date(2024, 1, 3))

    assert tuple(row.trade_date for row in kospi_rows) == (date(2024, 1, 2), date(2024, 1, 3))
    assert tuple(row.trade_date for row in investor_rows) == (date(2024, 1, 2), date(2024, 1, 3))
    assert tuple(row.trade_date for row in valuation_rows) == (date(2024, 1, 2), date(2024, 1, 3))


@pytest.mark.requires_network
@pytest.mark.skipif(
    os.getenv("KOSPI_PIPELINE_LIVE_KRX") != "1",
    reason="set KOSPI_PIPELINE_LIVE_KRX=1 to run live KRX smoke test",
)
def test_pykrx_krx_connector_live_smoke() -> None:
    connector = PykrxKrxConnector()

    rows = connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 5))

    assert rows
    assert rows == tuple(sorted(rows, key=lambda row: row.trade_date))
    assert all(row.metadata.connector_id.endswith("PykrxKrxConnector") for row in rows)
