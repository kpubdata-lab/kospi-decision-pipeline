from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol, cast

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import (
    FixtureDataPortalConnector,
    FixtureEcosConnector,
    FixtureKosisConnector,
    FixtureKrxConnector,
)
from kospi_decision_pipeline_app_kr_kospi.ingest import bronze as bronze_module
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import (
    BronzeIngestor,
    FixtureConnectorRegistry,
    LiveConnectorRegistry,
)
from kospi_decision_pipeline_app_kr_kospi.ingest.manifests import (
    BronzeManifest,
    read_manifest,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


class _NormalizeScalar(Protocol):
    def __call__(self, value: object) -> str | int: ...


class _RowToRecord(Protocol):
    def __call__(self, row: object) -> dict[str, str | int]: ...


normalize_scalar = cast(_NormalizeScalar, getattr(bronze_module, "_normalize_scalar"))
row_to_record = cast(_RowToRecord, getattr(bronze_module, "_row_to_record"))


@pytest.mark.parametrize(
    ("connector", "dataset_id", "source_name"),
    [
        (FixtureKrxConnector(FIXTURES_ROOT), "kospi_index", "krx"),
        (FixtureKrxConnector(FIXTURES_ROOT), "investor_flow", "krx"),
        (FixtureKrxConnector(FIXTURES_ROOT), "market_valuation", "krx"),
        (FixtureEcosConnector(FIXTURES_ROOT), "base_rate", "ecos"),
        (FixtureEcosConnector(FIXTURES_ROOT), "usd_krw", "ecos"),
        (FixtureEcosConnector(FIXTURES_ROOT), "bond_yield", "ecos"),
        (FixtureKosisConnector(FIXTURES_ROOT), "per_pbr_percentiles", "kosis"),
        (FixtureKosisConnector(FIXTURES_ROOT), "macro_indicators", "kosis"),
        (FixtureDataPortalConnector(FIXTURES_ROOT), "sample_dataset", "data_portal"),
    ],
)
def test_bronze_ingest_supports_all_fixture_datasets(
    tmp_path: Path, connector: object, dataset_id: str, source_name: str
) -> None:
    ingestor = BronzeIngestor(output_root=tmp_path, deterministic_run_timestamp=RUN_TIMESTAMP)

    result = ingestor.ingest(
        connector=connector,
        dataset_id=dataset_id,
        start=date(2024, 1, 2),
        end=date(2024, 1, 4),
    )

    assert result.entries
    assert all(entry.path.parts[0] == source_name for entry in result.entries)


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


def test_bronze_ingest_uses_current_time_when_no_deterministic_timestamp(tmp_path: Path) -> None:
    connector = FixtureKrxConnector(FIXTURES_ROOT)
    ingestor = BronzeIngestor(output_root=tmp_path)

    result = ingestor.ingest(
        connector=connector,
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )
    manifest = read_manifest(result.manifest_path)

    assert manifest.run_timestamp.tzinfo == timezone.utc
    assert manifest.run_timestamp.microsecond == 0


def test_fixture_connector_registry_returns_expected_connectors() -> None:
    registry = FixtureConnectorRegistry(FIXTURES_ROOT)

    assert isinstance(registry.get_connector("krx"), FixtureKrxConnector)
    assert isinstance(registry.get_connector("ecos"), FixtureEcosConnector)
    assert isinstance(registry.get_connector("kosis"), FixtureKosisConnector)
    assert isinstance(registry.get_connector("data_portal"), FixtureDataPortalConnector)


def test_fixture_connector_registry_rejects_unknown_source() -> None:
    registry = FixtureConnectorRegistry(FIXTURES_ROOT)

    with pytest.raises(ValueError, match="unsupported source"):
        registry.get_connector("missing")


def test_live_connector_registry_is_a_non_ci_hook() -> None:
    registry = LiveConnectorRegistry()

    with pytest.raises(NotImplementedError, match="live connector not implemented"):
        registry.get_connector("ecos")


def test_row_to_record_rejects_non_mapping_metadata() -> None:
    @dataclass(frozen=True, slots=True)
    class BrokenRow:
        metadata: object
        trade_date: date

    broken_row = BrokenRow(metadata="broken", trade_date=date(2024, 1, 2))

    with pytest.raises(ValueError, match="metadata"):
        row_to_record(broken_row)


def test_normalize_scalar_handles_boolean_branch() -> None:
    assert normalize_scalar(True) == "true"


def test_read_manifest_rejects_non_object_payload(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _ = manifest_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest payload must be an object"):
        read_manifest(manifest_path)
