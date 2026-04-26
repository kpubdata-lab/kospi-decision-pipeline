from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime

import pytest

from kospi_decision_pipeline_core.connectors import ConnectorRow, SourceMetadata


@dataclass(frozen=True, slots=True)
class SampleConnectorRow:
    metadata: SourceMetadata
    value: str


def test_source_metadata_captures_snapshot_connector_identity_fields() -> None:
    metadata = SourceMetadata(
        source_name="krx",
        dataset_name="kospi_index",
        fetched_at_utc="2024-01-10T09:00:00+00:00",
        connector_id="fixture.krx.FixtureKrxConnector",
        api_version="v1",
        key_fingerprint_sha256="abc123",
    )

    assert metadata.source_name == "krx"
    assert metadata.dataset_name == "kospi_index"
    assert metadata.fetched_at_utc == "2024-01-10T09:00:00+00:00"
    assert metadata.connector_id == "fixture.krx.FixtureKrxConnector"
    assert metadata.api_version == "v1"
    assert metadata.key_fingerprint_sha256 == "abc123"
    assert metadata.source_series_id == "kospi_index"
    assert metadata.fetched_at == datetime(2024, 1, 10, 9, 0, tzinfo=UTC)


def test_source_metadata_is_frozen() -> None:
    metadata = SourceMetadata(
        source_name="krx",
        dataset_name="kospi_index",
        fetched_at_utc="2024-01-10T09:00:00+00:00",
        connector_id="fixture.krx.FixtureKrxConnector",
    )

    with pytest.raises(FrozenInstanceError):
        metadata.source_name = "ecos"


def test_connector_row_protocol_accepts_typed_dataclass_rows() -> None:
    row = SampleConnectorRow(
        metadata=SourceMetadata(
            source_name="krx",
            dataset_name="kospi_index",
            fetched_at_utc="2024-01-10T09:00:00+00:00",
            connector_id="fixture.krx.FixtureKrxConnector",
        ),
        value="ok",
    )

    assert isinstance(row, ConnectorRow)


def test_source_metadata_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC"):
        SourceMetadata(
            source_name="krx",
            dataset_name="kospi_index",
            fetched_at_utc="2024-01-10T18:00:00+09:00",
            connector_id="fixture.krx.FixtureKrxConnector",
        )
