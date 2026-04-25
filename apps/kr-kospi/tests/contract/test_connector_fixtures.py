from __future__ import annotations

from collections.abc import Callable
from datetime import date
import importlib
from pathlib import Path
import sys
from typing import Protocol, TypeVar

import pytest

from kospi_decision_pipeline_app_kr_kospi import connectors
from kospi_decision_pipeline_app_kr_kospi.connectors.base import SourceMetadata
from kospi_decision_pipeline_app_kr_kospi.connectors.data_portal import (
    DataPortalConnector,
    DataPortalSampleRow,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import (
    EcosBaseRateRow,
    EcosBondYieldRow,
    EcosConnector,
    EcosUsdKrwRow,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import (
    FixtureDataPortalConnector,
    FixtureEcosConnector,
    FixtureKosisConnector,
    FixtureKrxConnector,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import (
    KosisMacroIndicatorRow,
    KosisConnector,
    PerPbrPercentileRow,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    KrxConnector,
    MarketValuationRow,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RowT = TypeVar("RowT")
START_DATE = date(2024, 1, 2)
END_DATE = date(2024, 1, 4)


class HasMetadata(Protocol):
    @property
    def metadata(self) -> SourceMetadata: ...


def assert_metadata(rows: tuple[HasMetadata, ...], source_name: str, source_series_id: str) -> None:
    assert rows
    for row in rows:
        metadata = row.metadata
        assert metadata.source_name == source_name
        assert metadata.source_series_id == source_series_id
        assert metadata.fetched_at.isoformat() == "2024-01-10T09:00:00+00:00"


def assert_deterministic(fetcher: Callable[[], tuple[RowT, ...]]) -> tuple[RowT, ...]:
    first_result = fetcher()
    second_result = fetcher()
    assert first_result == second_result
    return first_result


def test_fixture_krx_connector_satisfies_protocols_and_returns_typed_rows() -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)

    assert isinstance(connector, KrxConnector)

    kospi_rows = assert_deterministic(lambda: connector.fetch_kospi_index(START_DATE, END_DATE))
    investor_rows = assert_deterministic(
        lambda: connector.fetch_investor_flow(START_DATE, END_DATE)
    )
    valuation_rows = assert_deterministic(
        lambda: connector.fetch_market_valuation(START_DATE, END_DATE)
    )

    assert kospi_rows == tuple(kospi_rows)
    assert investor_rows == tuple(investor_rows)
    assert valuation_rows == tuple(valuation_rows)
    assert len(kospi_rows) == 3
    assert kospi_rows[0].trade_date == START_DATE
    assert kospi_rows[-1].trade_date == END_DATE
    assert all(isinstance(row, KospiIndexRow) for row in kospi_rows)
    assert all(isinstance(row, InvestorFlowRow) for row in investor_rows)
    assert all(isinstance(row, MarketValuationRow) for row in valuation_rows)
    assert_metadata(kospi_rows, source_name="krx", source_series_id="kospi_index")
    assert_metadata(investor_rows, source_name="krx", source_series_id="investor_flow")
    assert_metadata(valuation_rows, source_name="krx", source_series_id="market_valuation")


def test_fixture_ecos_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureEcosConnector(FIXTURES_ROOT)

    assert isinstance(connector, EcosConnector)

    rows = assert_deterministic(lambda: connector.fetch_base_rate_series(START_DATE, END_DATE))
    usd_krw_rows = assert_deterministic(
        lambda: connector.fetch_usd_krw_series(START_DATE, END_DATE)
    )
    bond_rows = assert_deterministic(
        lambda: connector.fetch_bond_yield_series(START_DATE, END_DATE)
    )

    assert all(isinstance(row, EcosBaseRateRow) for row in rows)
    assert all(isinstance(row, EcosUsdKrwRow) for row in usd_krw_rows)
    assert all(isinstance(row, EcosBondYieldRow) for row in bond_rows)
    assert_metadata(rows, source_name="ecos", source_series_id="base_rate")
    assert_metadata(usd_krw_rows, source_name="ecos", source_series_id="usd_krw")
    assert_metadata(bond_rows, source_name="ecos", source_series_id="bond_yield")


def test_fixture_kosis_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureKosisConnector(FIXTURES_ROOT)

    assert isinstance(connector, KosisConnector)

    rows = assert_deterministic(lambda: connector.fetch_per_pbr_percentiles(START_DATE, END_DATE))
    macro_rows = assert_deterministic(
        lambda: connector.fetch_macro_indicators(START_DATE, END_DATE)
    )

    assert all(isinstance(row, PerPbrPercentileRow) for row in rows)
    assert all(isinstance(row, KosisMacroIndicatorRow) for row in macro_rows)
    assert_metadata(rows, source_name="kosis", source_series_id="per_pbr_percentiles")
    assert_metadata(macro_rows, source_name="kosis", source_series_id="macro_indicators")


def test_fixture_data_portal_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureDataPortalConnector(FIXTURES_ROOT)

    assert isinstance(connector, DataPortalConnector)

    rows = assert_deterministic(lambda: connector.fetch_sample_dataset(START_DATE, END_DATE))

    assert all(isinstance(row, DataPortalSampleRow) for row in rows)
    assert_metadata(rows, source_name="data_portal", source_series_id="sample_dataset")


def test_fixture_connectors_do_not_require_network() -> None:
    krx_connector = FixtureKrxConnector(FIXTURES_ROOT)
    ecos_connector = FixtureEcosConnector(FIXTURES_ROOT)
    kosis_connector = FixtureKosisConnector(FIXTURES_ROOT)
    data_portal_connector = FixtureDataPortalConnector(FIXTURES_ROOT)

    assert krx_connector.fetch_kospi_index(START_DATE, END_DATE)
    assert krx_connector.fetch_investor_flow(START_DATE, END_DATE)
    assert krx_connector.fetch_market_valuation(START_DATE, END_DATE)
    assert ecos_connector.fetch_base_rate_series(START_DATE, END_DATE)
    assert ecos_connector.fetch_usd_krw_series(START_DATE, END_DATE)
    assert ecos_connector.fetch_bond_yield_series(START_DATE, END_DATE)
    assert kosis_connector.fetch_per_pbr_percentiles(START_DATE, END_DATE)
    assert kosis_connector.fetch_macro_indicators(START_DATE, END_DATE)
    assert data_portal_connector.fetch_sample_dataset(START_DATE, END_DATE)


def test_connectors_package_exports_fixture_connectors() -> None:
    assert connectors.FixtureKrxConnector is FixtureKrxConnector
    assert connectors.FixtureEcosConnector is FixtureEcosConnector
    assert connectors.FixtureKosisConnector is FixtureKosisConnector
    assert connectors.FixtureDataPortalConnector is FixtureDataPortalConnector


def test_connector_modules_do_not_read_fixtures_at_import_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported_modules = (
        "kospi_decision_pipeline_app_kr_kospi.connectors.base",
        "kospi_decision_pipeline_app_kr_kospi.connectors.krx",
        "kospi_decision_pipeline_app_kr_kospi.connectors.ecos",
        "kospi_decision_pipeline_app_kr_kospi.connectors.kosis",
        "kospi_decision_pipeline_app_kr_kospi.connectors.data_portal",
        "kospi_decision_pipeline_app_kr_kospi.connectors.fixture",
    )

    def fail_read_text(self: Path, encoding: str = "utf-8") -> str:
        raise AssertionError(f"fixture file should not be read at import time: {self} ({encoding})")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    for module_name in imported_modules:
        sys.modules.pop(module_name, None)
        importlib.import_module(module_name)
