from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
from typing import Protocol, cast

import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_app_kr_kospi.cli import main, run_ingest_command
from kospi_decision_pipeline_app_kr_kospi.connectors.base import SourceMetadata
from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import EcosBaseRateRow
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import LiveIngestManifest, read_manifest


RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


class _ArrowTable(Protocol):
    @property
    def num_rows(self) -> int: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))


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
            connector_registry=registry,
            deterministic_run_timestamp=RUN_TIMESTAMP,
        )
        == 0
    )

    manifest = read_manifest(
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "manifest.json"
    )

    assert registry.calls == [("ecos", None), ("ecos", None)]
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


def test_cli_main_live_ingest_writes_snapshot_partition_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connector = FakeLiveEcosConnector()
    registry = FakeLiveRegistry(connector)

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.LiveConnectorRegistry",
        lambda: registry,
    )

    exit_code = main(
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
            "--snapshot-id",
            "snapshot-20240115T000000Z",
            "--out",
            str(tmp_path),
        ]
    )

    manifest = read_manifest(
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "manifest.json"
    )

    assert exit_code == 0
    assert registry.calls == [("ecos", None)]
    assert connector.requested_ranges == [
        (date(2024, 1, 2), date(2024, 1, 2)),
        (date(2024, 1, 3), date(2024, 1, 3)),
    ]
    assert isinstance(manifest, LiveIngestManifest)
    assert [entry.path.as_posix() for entry in manifest.entries] == [
        "ecos/base_rate/2024-01-02.parquet",
        "ecos/base_rate/2024-01-03.parquet",
    ]
    assert (
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "2024-01-02.parquet"
    ).is_file()
    assert (
        tmp_path / "snapshot-20240115T000000Z" / "ecos" / "base_rate" / "2024-01-03.parquet"
    ).is_file()


def test_cli_main_fails_clearly_for_unsupported_live_kosis_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "ingest",
                "--live",
                "--source",
                "kosis",
                "--dataset",
                "per_pbr_percentiles",
                "--from",
                "2024-01-01",
                "--to",
                "2024-01-31",
                "--snapshot-id",
                "snapshot-20240115T000000Z",
                "--out",
                str(tmp_path),
            ]
        )
        == 1
    )

    assert "per_pbr_percentiles" in capsys.readouterr().err


@pytest.mark.requires_network
@pytest.mark.skipif(
    os.getenv("KPUBDATA_KOSIS_API_KEY") is None,
    reason="KPUBDATA_KOSIS_API_KEY not set",
)
def test_run_ingest_command_live_kosis_writes_verified_bronze_partition(tmp_path: Path) -> None:
    assert (
        run_ingest_command(
            source="kosis",
            dataset="macro_indicators",
            start="2024-01-01",
            end="2024-03-31",
            output_dir=str(tmp_path),
            live=True,
            snapshot_id="snapshot-20240301T000000Z",
            connector_registry=None,
            deterministic_run_timestamp=RUN_TIMESTAMP,
        )
        == 0
    )

    dataset_root = tmp_path / "snapshot-20240301T000000Z" / "kosis" / "macro_indicators"
    parquet_paths = sorted(dataset_root.glob("*.parquet"))

    assert parquet_paths
    first_table = READ_TABLE(parquet_paths[0])
    assert first_table.num_rows > 0
