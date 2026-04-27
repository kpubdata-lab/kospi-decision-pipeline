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
EcosRow = EcosBaseRateRow | EcosUsdKrwRow | EcosBondYieldRow


def _fetch_base_rate(connector: LiveEcosConnector, start: date, end: date) -> EcosRows:
    return connector.fetch_base_rate_series(start, end)


def _fetch_usd_krw(connector: LiveEcosConnector, start: date, end: date) -> EcosRows:
    return connector.fetch_usd_krw_series(start, end)


def _fetch_bond_yield(connector: LiveEcosConnector, start: date, end: date) -> EcosRows:
    return connector.fetch_bond_yield_series(start, end)


def _base_rate_value(row: EcosBaseRateRow | EcosUsdKrwRow | EcosBondYieldRow) -> Decimal:
    if isinstance(row, EcosBaseRateRow):
        return row.base_rate
    if isinstance(row, EcosUsdKrwRow):
        return row.exchange_rate
    return row.yield_rate


def _value_date(row: EcosRow) -> date:
    return row.value_date


@pytest.mark.parametrize(
    ("dataset_name", "fetcher", "value_getter"),
    [
        (
            "base_rate",
            _fetch_base_rate,
            _base_rate_value,
        ),
        (
            "usd_krw",
            _fetch_usd_krw,
            _base_rate_value,
        ),
        (
            "bond_yield",
            _fetch_bond_yield,
            _base_rate_value,
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
    assert tuple(_value_date(row) for row in rows) == tuple(
        sorted(_value_date(row) for row in rows)
    )
