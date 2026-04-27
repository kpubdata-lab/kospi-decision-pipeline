from __future__ import annotations

from collections.abc import Callable
from datetime import date
import os

import pytest
from kpubdata import Client

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    MarketValuationRow,
    PykrxKrxConnector,
)


pytestmark = [pytest.mark.live]

KrxRows = tuple[KospiIndexRow, ...] | tuple[InvestorFlowRow, ...] | tuple[MarketValuationRow, ...]
KrxFetcher = Callable[[PykrxKrxConnector, date, date], KrxRows]
KrxRow = KospiIndexRow | InvestorFlowRow | MarketValuationRow


def _fetch_kospi_index(connector: PykrxKrxConnector, start: date, end: date) -> KrxRows:
    return connector.fetch_kospi_index(start, end)


def _fetch_investor_flow(connector: PykrxKrxConnector, start: date, end: date) -> KrxRows:
    return connector.fetch_investor_flow(start, end)


def _fetch_market_valuation(connector: PykrxKrxConnector, start: date, end: date) -> KrxRows:
    return connector.fetch_market_valuation(start, end)


def _trade_date(row: KrxRow) -> date:
    return row.trade_date


@pytest.mark.skipif(
    os.getenv("KOSPI_PIPELINE_LIVE_KRX") != "1",
    reason="set KOSPI_PIPELINE_LIVE_KRX=1 to run live KRX tests",
)
@pytest.mark.parametrize(
    ("dataset_name", "fetcher", "date_getter"),
    [
        (
            "kospi_index",
            _fetch_kospi_index,
            _trade_date,
        ),
        (
            "investor_flow",
            _fetch_investor_flow,
            _trade_date,
        ),
        (
            "market_valuation",
            _fetch_market_valuation,
            _trade_date,
        ),
    ],
)
def test_pykrx_krx_connector_live_fetch_methods_return_sorted_rows(
    dataset_name: str,
    fetcher: KrxFetcher,
    date_getter: Callable[[KospiIndexRow | InvestorFlowRow | MarketValuationRow], date],
) -> None:
    connector = PykrxKrxConnector(client=Client.from_env())

    rows = fetcher(connector, date(2024, 1, 2), date(2024, 1, 5))

    assert rows
    assert rows[0].metadata.source_name == "krx"
    assert rows[0].metadata.dataset_name == dataset_name
    assert tuple(date_getter(row) for row in rows) == tuple(
        sorted(date_getter(row) for row in rows)
    )
    assert all(row.metadata.connector_id.endswith("PykrxKrxConnector") for row in rows)
