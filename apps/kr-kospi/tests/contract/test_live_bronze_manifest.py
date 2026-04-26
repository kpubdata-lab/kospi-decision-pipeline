from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol, cast

import pyarrow.parquet as pq

from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import FixtureKrxConnector
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import BronzeIngestor
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import LiveIngestManifest, read_manifest


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ReadTable(Protocol):
    def __call__(self, where: Path) -> _ArrowTable: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))


def test_snapshot_aware_ingest_writes_snapshot_root_and_live_manifest(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    result = ingestor.ingest(
        connector=connector,
        source="krx",
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 6),
        snapshot_id="snapshot-20240115T000000Z",
    )

    assert [entry.path for entry in result.entries] == [
        Path("krx/kospi_index/2024-01-02.parquet"),
        Path("krx/kospi_index/2024-01-03.parquet"),
        Path("krx/kospi_index/2024-01-04.parquet"),
        Path("krx/kospi_index/2024-01-05.parquet"),
    ]
    assert all(
        (tmp_path / "snapshot-20240115T000000Z" / entry.path).is_file() for entry in result.entries
    )

    manifest = read_manifest(result.manifest_path)

    assert isinstance(manifest, LiveIngestManifest)
    assert manifest.snapshot_id == "snapshot-20240115T000000Z"
    assert manifest.requested_start == date(2024, 1, 2)
    assert manifest.requested_end == date(2024, 1, 6)
    assert manifest.written_dates == (
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    )
    assert manifest.skipped_dates == (date(2024, 1, 6),)
    assert manifest.failed_dates == ()
    assert manifest.source_metadata.source_name == "krx"
    assert manifest.source_metadata.dataset_name == "kospi_index"
    assert manifest.source_metadata.connector_id.endswith("FixtureKrxConnector")
    assert manifest.source_metadata.fetched_at_utc == RUN_TIMESTAMP.isoformat()
    assert manifest.to_deterministic_dict()["snapshot_id"] == "snapshot-20240115T000000Z"


def test_live_ingest_rerun_skips_existing_snapshot_partitions(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    first_result = ingestor.ingest(
        connector=connector,
        source="krx",
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        snapshot_id="snapshot-20240115T000000Z",
    )
    existing_partition = (
        tmp_path / "snapshot-20240115T000000Z" / "krx" / "kospi_index" / "2024-01-02.parquet"
    )
    baseline_rows = READ_TABLE(existing_partition).to_pylist()

    rerun_result = ingestor.ingest(
        connector=connector,
        source="krx",
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 4),
        snapshot_id="snapshot-20240115T000000Z",
    )
    rerun_manifest = read_manifest(rerun_result.manifest_path)

    assert first_result.entries
    assert [entry.path for entry in rerun_result.entries] == [
        Path("krx/kospi_index/2024-01-04.parquet"),
    ]
    assert isinstance(rerun_manifest, LiveIngestManifest)
    assert rerun_manifest.written_dates == (date(2024, 1, 4),)
    assert rerun_manifest.skipped_dates == (date(2024, 1, 2), date(2024, 1, 3))
    assert rerun_manifest.failed_dates == ()
    assert READ_TABLE(existing_partition).to_pylist() == baseline_rows
