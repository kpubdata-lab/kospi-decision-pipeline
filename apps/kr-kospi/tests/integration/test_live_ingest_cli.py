from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from kospi_decision_pipeline_app_kr_kospi.cli import main, run_ingest_command
from kospi_decision_pipeline_app_kr_kospi.connectors.base import SourceMetadata
from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import EcosBaseRateRow
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import LiveIngestManifest, read_manifest


RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeLiveEcosConnector:
    requested_ranges: list[tuple[date, date]] = field(default_factory=list)

    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]:
        self.requested_ranges.append((start, end))
        if start == date(2024, 1, 2):
            return (
                EcosBaseRateRow(
                    metadata=SourceMetadata(
                        source_name="ecos",
                        dataset_name="base_rate",
                        fetched_at_utc=RUN_TIMESTAMP.isoformat(),
                        connector_id="tests.integration.FakeLiveEcosConnector",
                        api_version="fake-v1",
                        key_fingerprint_sha256="fake-fingerprint",
                    ),
                    value_date=start,
                    base_rate=Decimal("3.50"),
                ),
            )
        if start == date(2024, 1, 3):
            return (
                EcosBaseRateRow(
                    metadata=SourceMetadata(
                        source_name="ecos",
                        dataset_name="base_rate",
                        fetched_at_utc=RUN_TIMESTAMP.isoformat(),
                        connector_id="tests.integration.FakeLiveEcosConnector",
                        api_version="fake-v1",
                        key_fingerprint_sha256="fake-fingerprint",
                    ),
                    value_date=start,
                    base_rate=Decimal("3.50"),
                ),
            )
        return ()


class FakeLiveRegistry:
    def __init__(self, connector: FakeLiveEcosConnector) -> None:
        self.connector = connector
        self.calls: list[tuple[str, str | None]] = []

    def get_connector(self, source: str, *, api_key: str | None = None) -> object:
        self.calls.append((source, api_key))
        return self.connector


def test_cli_main_requires_snapshot_id_for_live_ingest(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="2"):
        _ = main(
            [
                "ingest",
                "--live",
                "--source",
                "ecos",
                "--dataset",
                "base_rate",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-03",
            ]
        )

    assert "--snapshot-id is required when live ingest is enabled" in capsys.readouterr().err


def test_run_ingest_command_live_mode_is_idempotent_for_existing_snapshot_partitions(
    tmp_path: Path,
) -> None:
    connector = FakeLiveEcosConnector()
    registry = FakeLiveRegistry(connector)

    assert (
        run_ingest_command(
            source="ecos",
            dataset="base_rate",
            start="2024-01-02",
            end="2024-01-03",
            output_dir=str(tmp_path),
            live=True,
            snapshot_id="snapshot-20240115T000000Z",
            api_key="cli-key",
            connector_registry=registry,
            deterministic_run_timestamp=RUN_TIMESTAMP,
        )
        == 0
    )
    assert connector.requested_ranges == [
        (date(2024, 1, 2), date(2024, 1, 2)),
        (date(2024, 1, 3), date(2024, 1, 3)),
    ]

    connector.requested_ranges.clear()
    assert (
        run_ingest_command(
            source="ecos",
            dataset="base_rate",
            start="2024-01-02",
            end="2024-01-03",
            output_dir=str(tmp_path),
            live=True,
            snapshot_id="snapshot-20240115T000000Z",
            api_key="cli-key",
            connector_registry=registry,
            deterministic_run_timestamp=RUN_TIMESTAMP,
        )
        == 0
    )

    manifest = read_manifest(
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "manifest.json"
    )

    assert registry.calls == [("ecos", "cli-key"), ("ecos", "cli-key")]
    assert connector.requested_ranges == []
    assert isinstance(manifest, LiveIngestManifest)
    assert manifest.written_dates == ()
    assert manifest.skipped_dates == (date(2024, 1, 2), date(2024, 1, 3))
    assert manifest.failed_dates == ()
    assert (
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "2024-01-02.parquet"
    ).is_file()
    assert (
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "2024-01-03.parquet"
    ).is_file()
