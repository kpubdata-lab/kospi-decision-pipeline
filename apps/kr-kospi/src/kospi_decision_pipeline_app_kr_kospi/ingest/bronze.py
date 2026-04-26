from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Protocol, cast, final

import pyarrow as _pa
import pyarrow.parquet as _pq

from ..connectors import (
    DataPortalConnector,
    EcosConnector,
    FixtureDataPortalConnector,
    FixtureEcosConnector,
    FixtureKosisConnector,
    FixtureKrxConnector,
    KosisConnector,
    KrxConnector,
)
from ..connectors.base import ConnectorRowBase, SourceMetadata
from .manifests import BronzeManifest, LiveIngestManifest, ManifestEntry, write_manifest


SourceName = str
DatasetId = str


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, str | int]]) -> object: ...


class _ParquetWriter(Protocol):
    def write_table(self, table: object, where: Path, *, compression: str) -> None: ...


ARROW_TABLE = cast(_ArrowTableFactory, _pa.Table)
PARQUET_WRITER: _ParquetWriter = _pq


@dataclass(frozen=True, slots=True)
class BronzeIngestResult:
    entries: tuple[ManifestEntry, ...]
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class _DatasetDefinition:
    source_name: str
    date_field_name: str
    fetch_rows: _FetchRows


class _FetchRows(Protocol):
    def __call__(
        self, connector: object, start: date, end: date
    ) -> tuple[ConnectorRowBase, ...]: ...


def _fetch_krx_kospi_index(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_kospi_index(start, end))


def _fetch_krx_investor_flow(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_investor_flow(start, end))


def _fetch_krx_market_valuation(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_market_valuation(start, end))


def _fetch_ecos_base_rate(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_base_rate_series(start, end))


def _fetch_ecos_usd_krw(connector: object, start: date, end: date) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_usd_krw_series(start, end))


def _fetch_ecos_bond_yield(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_bond_yield_series(start, end))


def _fetch_kosis_per_pbr(connector: object, start: date, end: date) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(KosisConnector, connector)
    return tuple(typed_connector.fetch_per_pbr_percentiles(start, end))


def _fetch_kosis_macro(connector: object, start: date, end: date) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(KosisConnector, connector)
    return tuple(typed_connector.fetch_macro_indicators(start, end))


def _fetch_data_portal_sample(
    connector: object, start: date, end: date
) -> tuple[ConnectorRowBase, ...]:
    typed_connector = cast(DataPortalConnector, connector)
    return tuple(typed_connector.fetch_sample_dataset(start, end))


DATASET_DEFINITIONS: dict[str, _DatasetDefinition] = {
    "kospi_index": _DatasetDefinition(
        source_name="krx",
        date_field_name="trade_date",
        fetch_rows=_fetch_krx_kospi_index,
    ),
    "investor_flow": _DatasetDefinition(
        source_name="krx",
        date_field_name="trade_date",
        fetch_rows=_fetch_krx_investor_flow,
    ),
    "market_valuation": _DatasetDefinition(
        source_name="krx",
        date_field_name="trade_date",
        fetch_rows=_fetch_krx_market_valuation,
    ),
    "base_rate": _DatasetDefinition(
        source_name="ecos",
        date_field_name="value_date",
        fetch_rows=_fetch_ecos_base_rate,
    ),
    "usd_krw": _DatasetDefinition(
        source_name="ecos",
        date_field_name="value_date",
        fetch_rows=_fetch_ecos_usd_krw,
    ),
    "bond_yield": _DatasetDefinition(
        source_name="ecos",
        date_field_name="value_date",
        fetch_rows=_fetch_ecos_bond_yield,
    ),
    "per_pbr_percentiles": _DatasetDefinition(
        source_name="kosis",
        date_field_name="value_date",
        fetch_rows=_fetch_kosis_per_pbr,
    ),
    "macro_indicators": _DatasetDefinition(
        source_name="kosis",
        date_field_name="value_date",
        fetch_rows=_fetch_kosis_macro,
    ),
    "sample_dataset": _DatasetDefinition(
        source_name="data_portal",
        date_field_name="value_date",
        fetch_rows=_fetch_data_portal_sample,
    ),
}


@final
class BronzeIngestor:
    _output_root: Path
    _deterministic_run_timestamp: datetime | None

    def __init__(
        self, output_root: Path, deterministic_run_timestamp: datetime | None = None
    ) -> None:
        self._output_root = output_root
        self._deterministic_run_timestamp = deterministic_run_timestamp

    def ingest(
        self,
        connector: object,
        source: str,
        dataset_id: str,
        start: date,
        end: date,
        snapshot_id: str | None = None,
    ) -> BronzeIngestResult:
        definition = DATASET_DEFINITIONS.get(dataset_id)
        if definition is None:
            raise ValueError(f"unsupported dataset: {dataset_id}")
        if definition.source_name != source:
            raise ValueError(f"dataset {dataset_id} is not supported for source {source}")

        run_timestamp = self._resolve_run_timestamp()
        if snapshot_id is None:
            rows = definition.fetch_rows(connector, start, end)
            grouped_rows = _group_rows_by_date(rows, definition.date_field_name)
            entries = tuple(
                self._write_partition(
                    source_name=definition.source_name,
                    dataset_id=dataset_id,
                    as_of_date=as_of_date,
                    rows=partition_rows,
                    snapshot_id=snapshot_id,
                )
                for as_of_date, partition_rows in grouped_rows
            )
            manifest: BronzeManifest = BronzeManifest(
                dataset_id=dataset_id,
                source_name=definition.source_name,
                run_timestamp=run_timestamp,
                entries=entries,
            )
        else:
            live_result = self._ingest_live_partitions(
                connector=connector,
                definition=definition,
                dataset_id=dataset_id,
                start=start,
                end=end,
                snapshot_id=snapshot_id,
            )
            manifest = LiveIngestManifest(
                dataset_id=dataset_id,
                source_name=definition.source_name,
                run_timestamp=run_timestamp,
                entries=live_result.entries,
                snapshot_id=snapshot_id,
                requested_start=start,
                requested_end=end,
                written_dates=live_result.written_dates,
                skipped_dates=live_result.skipped_dates,
                failed_dates=live_result.failed_dates,
                source_metadata=_live_source_metadata(
                    connector=connector,
                    source_name=definition.source_name,
                    dataset_id=dataset_id,
                    fetched_at=run_timestamp,
                    sample_row=live_result.sample_row,
                ),
            )
            entries = live_result.entries
        manifest_path = (
            self._output_root_for_snapshot(snapshot_id)
            / definition.source_name
            / dataset_id
            / "manifest.json"
        )
        write_manifest(manifest_path, manifest)
        return BronzeIngestResult(entries=entries, manifest_path=manifest_path)

    def _resolve_run_timestamp(self) -> datetime:
        if self._deterministic_run_timestamp is not None:
            return self._deterministic_run_timestamp
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _ingest_live_partitions(
        self,
        *,
        connector: object,
        definition: _DatasetDefinition,
        dataset_id: str,
        start: date,
        end: date,
        snapshot_id: str,
    ) -> _LivePartitionIngestResult:
        entries: list[ManifestEntry] = []
        written_dates: list[date] = []
        skipped_dates: list[date] = []
        failed_dates: list[date] = []
        sample_row: ConnectorRowBase | None = None

        current = start
        while current <= end:
            if self._partition_output_path(
                source_name=definition.source_name,
                dataset_id=dataset_id,
                as_of_date=current,
                snapshot_id=snapshot_id,
            ).is_file():
                skipped_dates.append(current)
                current = current.fromordinal(current.toordinal() + 1)
                continue

            try:
                rows = definition.fetch_rows(connector, current, current)
            except Exception:
                failed_dates.append(current)
                current = current.fromordinal(current.toordinal() + 1)
                continue

            grouped_rows = _group_rows_by_date(rows, definition.date_field_name)
            if len(grouped_rows) == 0:
                skipped_dates.append(current)
                current = current.fromordinal(current.toordinal() + 1)
                continue

            for as_of_date, partition_rows in grouped_rows:
                entries.append(
                    self._write_partition(
                        source_name=definition.source_name,
                        dataset_id=dataset_id,
                        as_of_date=as_of_date,
                        rows=partition_rows,
                        snapshot_id=snapshot_id,
                    )
                )
                written_dates.append(as_of_date)
                if sample_row is None:
                    sample_row = partition_rows[0]
            current = current.fromordinal(current.toordinal() + 1)

        return _LivePartitionIngestResult(
            entries=tuple(entries),
            written_dates=tuple(written_dates),
            skipped_dates=tuple(skipped_dates),
            failed_dates=tuple(failed_dates),
            sample_row=sample_row,
        )

    def _write_partition(
        self,
        source_name: str,
        dataset_id: str,
        as_of_date: date,
        rows: tuple[ConnectorRowBase, ...],
        snapshot_id: str | None,
    ) -> ManifestEntry:
        relative_path = Path(source_name) / dataset_id / f"{as_of_date.isoformat()}.parquet"
        output_path = self._partition_output_path(
            source_name=source_name,
            dataset_id=dataset_id,
            as_of_date=as_of_date,
            snapshot_id=snapshot_id,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        records = [_row_to_record(row) for row in rows]
        sorted_records = tuple(sorted(records, key=_record_sort_key))
        table = ARROW_TABLE.from_pylist(list(sorted_records))
        PARQUET_WRITER.write_table(table, output_path, compression="snappy")

        return ManifestEntry(
            path=relative_path,
            sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
            row_count=len(sorted_records),
            fetched_at=str(sorted_records[0]["fetched_at"]),
        )

    def _output_root_for_snapshot(self, snapshot_id: str | None) -> Path:
        if snapshot_id is None:
            return self._output_root
        return self._output_root / snapshot_id

    def _partition_output_path(
        self, *, source_name: str, dataset_id: str, as_of_date: date, snapshot_id: str | None
    ) -> Path:
        relative_path = Path(source_name) / dataset_id / f"{as_of_date.isoformat()}.parquet"
        return self._output_root_for_snapshot(snapshot_id) / relative_path


def _group_rows_by_date(
    rows: tuple[ConnectorRowBase, ...], date_field_name: str
) -> tuple[tuple[date, tuple[ConnectorRowBase, ...]], ...]:
    grouped: dict[date, list[ConnectorRowBase]] = {}
    for row in rows:
        as_of_date = cast(date, getattr(row, date_field_name))
        grouped.setdefault(as_of_date, []).append(row)
    return tuple((as_of_date, tuple(grouped[as_of_date])) for as_of_date in sorted(grouped))


def _row_to_record(row: ConnectorRowBase) -> dict[str, str | int]:
    payload = cast(dict[str, object], asdict(row))
    metadata = payload.pop("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("row metadata must serialize to a dictionary")
    metadata_payload = cast(dict[str, object], metadata)
    record: dict[str, str | int] = {
        "source_name": _normalize_scalar(metadata_payload["source_name"]),
        "source_series_id": _normalize_scalar(metadata_payload["dataset_name"]),
        "fetched_at": _normalize_scalar(metadata_payload["fetched_at_utc"]),
    }
    ordered_field_names = sorted(field.name for field in fields(row) if field.name != "metadata")
    for field_name in ordered_field_names:
        value = payload[field_name]
        record[field_name] = _normalize_scalar(value)
    return record


def _normalize_scalar(value: object) -> str | int:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _record_sort_key(record: dict[str, str | int]) -> tuple[str, ...]:
    return tuple(f"{key}={record[key]}" for key in sorted(record))


def _source_metadata(
    *, connector: object, source_name: str, dataset_id: str, fetched_at: datetime
) -> SourceMetadata:
    connector_type = type(connector)
    return SourceMetadata(
        source_name=source_name,
        dataset_name=dataset_id,
        fetched_at_utc=fetched_at.isoformat(),
        connector_id=f"{connector_type.__module__}.{connector_type.__qualname__}",
    )


def _live_source_metadata(
    *,
    connector: object,
    source_name: str,
    dataset_id: str,
    fetched_at: datetime,
    sample_row: ConnectorRowBase | None,
) -> SourceMetadata:
    if sample_row is not None:
        row_metadata = sample_row.metadata
        return SourceMetadata(
            source_name=row_metadata.source_name,
            dataset_name=row_metadata.dataset_name,
            fetched_at_utc=fetched_at.isoformat(),
            connector_id=row_metadata.connector_id,
            api_version=row_metadata.api_version,
            key_fingerprint_sha256=row_metadata.key_fingerprint_sha256,
        )
    return _source_metadata(
        connector=connector,
        source_name=source_name,
        dataset_id=dataset_id,
        fetched_at=fetched_at,
    )


class ConnectorRegistry(Protocol):
    def get_connector(self, source: str) -> object: ...


@dataclass(frozen=True, slots=True)
class _LivePartitionIngestResult:
    entries: tuple[ManifestEntry, ...]
    written_dates: tuple[date, ...]
    skipped_dates: tuple[date, ...]
    failed_dates: tuple[date, ...]
    sample_row: ConnectorRowBase | None


@final
class FixtureConnectorRegistry:
    _fixtures_root: Path

    def __init__(self, fixtures_root: Path) -> None:
        self._fixtures_root = fixtures_root

    def get_connector(self, source: str) -> object:
        registry: dict[str, object] = {
            "krx": FixtureKrxConnector(self._fixtures_root),
            "ecos": FixtureEcosConnector(self._fixtures_root),
            "kosis": FixtureKosisConnector(self._fixtures_root),
            "data_portal": FixtureDataPortalConnector(self._fixtures_root),
        }
        if source not in registry:
            raise ValueError(f"unsupported source: {source}")
        return registry[source]
