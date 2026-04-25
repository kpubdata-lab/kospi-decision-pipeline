from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import FixtureKrxConnector
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import BronzeIngestor
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import (
    BronzeManifest,
    read_manifest,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


def _run_ingest(output_root: Path) -> tuple[tuple[str, ...], BronzeManifest]:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=output_root, deterministic_run_timestamp=RUN_TIMESTAMP)
    result = ingestor.ingest(
        connector=connector,
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 4),
    )
    manifest = read_manifest(output_root / "krx" / "kospi_index" / "manifest.json")
    return tuple(entry.sha256 for entry in result.entries), manifest


def test_fixture_bronze_ingest_writes_partitioned_parquet_and_manifest(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    result = ingestor.ingest(
        connector=connector,
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 4),
    )

    written_paths = [entry.path for entry in result.entries]
    assert written_paths == [
        Path("krx/kospi_index/2024-01-02.parquet"),
        Path("krx/kospi_index/2024-01-03.parquet"),
        Path("krx/kospi_index/2024-01-04.parquet"),
    ]
    assert all((tmp_path / path).is_file() for path in written_paths)

    manifest = read_manifest(tmp_path / "krx" / "kospi_index" / "manifest.json")
    assert manifest.dataset_id == "kospi_index"
    assert manifest.source_name == "krx"
    assert manifest.run_timestamp == RUN_TIMESTAMP
    assert [entry.path for entry in manifest.entries] == written_paths
    assert [entry.row_count for entry in manifest.entries] == [1, 1, 1]
    assert [entry.fetched_at for entry in manifest.entries] == [
        "2024-01-10T09:00:00+00:00",
        "2024-01-10T09:00:00+00:00",
        "2024-01-10T09:00:00+00:00",
    ]


def test_fixture_bronze_ingest_is_deterministic_for_same_input(tmp_path: Path) -> None:
    first_hashes, first_manifest = _run_ingest(tmp_path / "run-one")
    second_hashes, second_manifest = _run_ingest(tmp_path / "run-two")

    assert first_hashes == second_hashes
    assert first_manifest.to_deterministic_dict() == second_manifest.to_deterministic_dict()


def test_manifest_round_trip_preserves_entries(tmp_path: Path) -> None:
    _, manifest = _run_ingest(tmp_path)

    assert manifest == BronzeManifest.from_dict(manifest.to_dict())


def test_bronze_ingest_raises_for_unknown_dataset(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    with pytest.raises(ValueError, match="unsupported dataset"):
        ingestor.ingest(
            connector=connector,
            dataset_id="missing_dataset",
            start=date(2024, 1, 2),
            end=date(2024, 1, 4),
        )
