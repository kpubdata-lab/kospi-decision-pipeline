from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
import os

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import (
    EcosBaseRateRow,
    EcosBondYieldRow,
    EcosUsdKrwRow,
    LiveEcosConnector,
)


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("ECOS_API_KEY") in {None, ""},
        reason="set ECOS_API_KEY to run live ECOS tests",
    ),
]

EcosRows = tuple[EcosBaseRateRow, ...] | tuple[EcosUsdKrwRow, ...] | tuple[EcosBondYieldRow, ...]
EcosFetcher = Callable[[LiveEcosConnector, date, date], EcosRows]


@pytest.mark.parametrize(
    ("dataset_name", "fetcher", "value_getter"),
    [
        (
            "base_rate",
            lambda connector, start, end: connector.fetch_base_rate_series(start, end),
            lambda row: row.base_rate,
        ),
        (
            "usd_krw",
            lambda connector, start, end: connector.fetch_usd_krw_series(start, end),
            lambda row: row.exchange_rate,
        ),
        (
            "bond_yield",
            lambda connector, start, end: connector.fetch_bond_yield_series(start, end),
            lambda row: row.yield_rate,
        ),
    ],
)
def test_live_ecos_connector_fetches_sorted_rows_for_all_series(
    dataset_name: str,
    fetcher: EcosFetcher,
    value_getter: Callable[[EcosBaseRateRow | EcosUsdKrwRow | EcosBondYieldRow], Decimal],
) -> None:
    connector = LiveEcosConnector()

    rows = fetcher(connector, date(2024, 1, 2), date(2024, 1, 5))

    assert rows
    first_row = rows[0]
    assert first_row.metadata.source_name == "ecos"
    assert first_row.metadata.dataset_name == dataset_name
    assert first_row.metadata.api_version == "StatisticSearch"
    assert first_row.metadata.key_fingerprint_sha256 is not None
    assert tuple(value_getter(row) for row in rows)
    assert rows == tuple(sorted(rows, key=lambda row: row.value_date))
