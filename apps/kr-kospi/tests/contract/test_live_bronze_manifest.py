from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import FixtureKrxConnector
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import BronzeIngestor
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import LiveIngestManifest, read_manifest


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


def test_snapshot_aware_ingest_writes_snapshot_root_and_live_manifest(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    result = ingestor.ingest(
        connector=connector,
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
