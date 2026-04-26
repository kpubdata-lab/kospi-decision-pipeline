from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import os

import pandas as pd
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    MarketValuationRow,
    PykrxKrxConnector,
)


class FakePykrxStockApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> pd.DataFrame:
        self.calls.append(
            (
                "get_index_ohlcv_by_date",
                (fromdate, todate, ticker),
                {"freq": freq, "name_display": name_display},
            )
        )
        if fromdate == "20240106":
            return pd.DataFrame(
                columns=["시가", "고가", "저가", "종가", "거래량", "거래대금", "상장시가총액"]
            )
        return pd.DataFrame(
            {
                "시가": [2660.0, 2640.5],
                "고가": [2672.1, 2655.0],
                "저가": [2631.5, 2621.0],
                "종가": [2645.2, 2651.8],
                "거래량": [460000000, 470000000],
                "거래대금": [Decimal("9100000000000"), Decimal("9200000000000")],
                "상장시가총액": [
                    Decimal("2100000000000000"),
                    Decimal("2110000000000000"),
                ],
            },
            index=pd.to_datetime(["2024-01-03", "2024-01-02"]),
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
    ) -> pd.DataFrame:
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
            return pd.DataFrame(columns=["개인", "외국인합계", "기관합계"])
        return pd.DataFrame(
            {
                "개인": [Decimal("-200000000000"), Decimal("100000000000")],
                "외국인합계": [Decimal("150000000000"), Decimal("-120000000000")],
                "기관합계": [Decimal("50000000000"), Decimal("20000000000")],
            },
            index=pd.to_datetime(["2024-01-03", "2024-01-02"]),
        )

    def get_index_fundamental_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        prev: bool = True,
    ) -> pd.DataFrame:
        self.calls.append(
            (
                "get_index_fundamental_by_date",
                (fromdate, todate, ticker),
                {"prev": prev},
            )
        )
        if fromdate == "20240106":
            return pd.DataFrame(columns=["PER", "PBR"])
        return pd.DataFrame(
            {
                "PER": [12.5, 12.2],
                "PBR": [0.95, 0.93],
            },
            index=pd.to_datetime(["2024-01-03", "2024-01-02"]),
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
    assert [call[1][:2] for call in stock_api.calls] == [
        ("20200101", "20211231"),
        ("20220101", "20231231"),
        ("20240101", "20241231"),
    ]
    assert sleep_calls == [1.0, 1.0]


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
