from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import socket
from typing import TypeVar

from kospi_decision_pipeline_app_kr_kospi.connectors.data_portal import (
    DataPortalConnector,
    DataPortalSampleRow,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import EcosConnector, EcosBaseRateRow
from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import (
    FixtureDataPortalConnector,
    FixtureEcosConnector,
    FixtureKosisConnector,
    FixtureKrxConnector,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import (
    KosisConnector,
    PerPbrPercentileRow,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    KrxConnector,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RowT = TypeVar("RowT")


def assert_metadata(rows: tuple[object, ...], source_name: str, source_series_id: str) -> None:
    assert rows
    first_row = rows[0]
    metadata = getattr(first_row, "metadata")
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

    kospi_rows = assert_deterministic(lambda: connector.fetch_kospi_index())
    investor_rows = assert_deterministic(lambda: connector.fetch_investor_flow())

    assert kospi_rows == tuple(kospi_rows)
    assert investor_rows == tuple(investor_rows)
    assert all(isinstance(row, KospiIndexRow) for row in kospi_rows)
    assert all(isinstance(row, InvestorFlowRow) for row in investor_rows)
    assert_metadata(kospi_rows, source_name="krx", source_series_id="kospi_index")
    assert_metadata(investor_rows, source_name="krx", source_series_id="investor_flow")


def test_fixture_ecos_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureEcosConnector(FIXTURES_ROOT)

    assert isinstance(connector, EcosConnector)

    rows = assert_deterministic(lambda: connector.fetch_base_rate_series())

    assert all(isinstance(row, EcosBaseRateRow) for row in rows)
    assert_metadata(rows, source_name="ecos", source_series_id="base_rate")


def test_fixture_kosis_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureKosisConnector(FIXTURES_ROOT)

    assert isinstance(connector, KosisConnector)

    rows = assert_deterministic(lambda: connector.fetch_per_pbr_percentiles())

    assert all(isinstance(row, PerPbrPercentileRow) for row in rows)
    assert_metadata(rows, source_name="kosis", source_series_id="per_pbr_percentiles")


def test_fixture_data_portal_connector_satisfies_protocol_and_returns_metadata() -> None:
    connector = FixtureDataPortalConnector(FIXTURES_ROOT)

    assert isinstance(connector, DataPortalConnector)

    rows = assert_deterministic(lambda: connector.fetch_sample_dataset())

    assert all(isinstance(row, DataPortalSampleRow) for row in rows)
    assert_metadata(rows, source_name="data_portal", source_series_id="sample_dataset")


def test_fixture_connectors_do_not_require_network(monkeypatch) -> None:
    def fail_connect(self: socket.socket, address: object) -> None:
        raise AssertionError(f"unexpected network access: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", fail_connect)

    krx_connector = FixtureKrxConnector(FIXTURES_ROOT)
    ecos_connector = FixtureEcosConnector(FIXTURES_ROOT)
    kosis_connector = FixtureKosisConnector(FIXTURES_ROOT)
    data_portal_connector = FixtureDataPortalConnector(FIXTURES_ROOT)

    assert krx_connector.fetch_kospi_index()
    assert krx_connector.fetch_investor_flow()
    assert ecos_connector.fetch_base_rate_series()
    assert kosis_connector.fetch_per_pbr_percentiles()
    assert data_portal_connector.fetch_sample_dataset()
