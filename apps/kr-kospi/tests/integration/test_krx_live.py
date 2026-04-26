from __future__ import annotations

from collections.abc import Callable
from datetime import date
import os

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    MarketValuationRow,
    PykrxKrxConnector,
)


pytestmark = [pytest.mark.live]

KrxRows = tuple[KospiIndexRow, ...] | tuple[InvestorFlowRow, ...] | tuple[MarketValuationRow, ...]
KrxFetcher = Callable[[PykrxKrxConnector, date, date], KrxRows]


@pytest.mark.skipif(
    os.getenv("KOSPI_PIPELINE_LIVE_KRX") != "1",
    reason="set KOSPI_PIPELINE_LIVE_KRX=1 to run live KRX tests",
)
@pytest.mark.parametrize(
    ("dataset_name", "fetcher", "date_getter"),
    [
        (
            "kospi_index",
            lambda connector, start, end: connector.fetch_kospi_index(start, end),
            lambda row: row.trade_date,
        ),
        (
            "investor_flow",
            lambda connector, start, end: connector.fetch_investor_flow(start, end),
            lambda row: row.trade_date,
        ),
        (
            "market_valuation",
            lambda connector, start, end: connector.fetch_market_valuation(start, end),
            lambda row: row.trade_date,
        ),
    ],
)
def test_pykrx_krx_connector_live_fetch_methods_return_sorted_rows(
    dataset_name: str,
    fetcher: KrxFetcher,
    date_getter: Callable[[KospiIndexRow | InvestorFlowRow | MarketValuationRow], date],
) -> None:
    connector = PykrxKrxConnector()

    rows = fetcher(connector, date(2024, 1, 2), date(2024, 1, 5))

    assert rows
    assert rows[0].metadata.source_name == "krx"
    assert rows[0].metadata.dataset_name == dataset_name
    assert rows == tuple(sorted(rows, key=date_getter))
    assert all(row.metadata.connector_id.endswith("PykrxKrxConnector") for row in rows)
