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
from ..connectors.base import ConnectorRow
from .manifests import BronzeManifest, ManifestEntry, write_manifest


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
    def __call__(self, connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]: ...


def _fetch_krx_kospi_index(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_kospi_index(start, end))


def _fetch_krx_investor_flow(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_investor_flow(start, end))


def _fetch_krx_market_valuation(
    connector: object, start: date, end: date
) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(KrxConnector, connector)
    return tuple(typed_connector.fetch_market_valuation(start, end))


def _fetch_ecos_base_rate(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_base_rate_series(start, end))


def _fetch_ecos_usd_krw(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_usd_krw_series(start, end))


def _fetch_ecos_bond_yield(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(EcosConnector, connector)
    return tuple(typed_connector.fetch_bond_yield_series(start, end))


def _fetch_kosis_per_pbr(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(KosisConnector, connector)
    return tuple(typed_connector.fetch_per_pbr_percentiles(start, end))


def _fetch_kosis_macro(connector: object, start: date, end: date) -> tuple[ConnectorRow, ...]:
    typed_connector = cast(KosisConnector, connector)
    return tuple(typed_connector.fetch_macro_indicators(start, end))


def _fetch_data_portal_sample(
    connector: object, start: date, end: date
) -> tuple[ConnectorRow, ...]:
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
        dataset_id: str,
        start: date,
        end: date,
    ) -> BronzeIngestResult:
        definition = DATASET_DEFINITIONS.get(dataset_id)
        if definition is None:
            raise ValueError(f"unsupported dataset: {dataset_id}")

        rows = definition.fetch_rows(connector, start, end)
        grouped_rows = _group_rows_by_date(rows, definition.date_field_name)
        entries = tuple(
            self._write_partition(
                source_name=definition.source_name,
                dataset_id=dataset_id,
                as_of_date=as_of_date,
                rows=partition_rows,
            )
            for as_of_date, partition_rows in grouped_rows
        )

        manifest = BronzeManifest(
            dataset_id=dataset_id,
            source_name=definition.source_name,
            run_timestamp=self._resolve_run_timestamp(),
            entries=entries,
        )
        manifest_path = self._output_root / definition.source_name / dataset_id / "manifest.json"
        write_manifest(manifest_path, manifest)
        return BronzeIngestResult(entries=entries, manifest_path=manifest_path)

    def _resolve_run_timestamp(self) -> datetime:
        if self._deterministic_run_timestamp is not None:
            return self._deterministic_run_timestamp
        return datetime.now(timezone.utc).replace(microsecond=0)

    def _write_partition(
        self,
        source_name: str,
        dataset_id: str,
        as_of_date: date,
        rows: tuple[ConnectorRow, ...],
    ) -> ManifestEntry:
        relative_path = Path(source_name) / dataset_id / f"{as_of_date.isoformat()}.parquet"
        output_path = self._output_root / relative_path
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


def _group_rows_by_date(
    rows: tuple[ConnectorRow, ...], date_field_name: str
) -> tuple[tuple[date, tuple[ConnectorRow, ...]], ...]:
    grouped: dict[date, list[ConnectorRow]] = {}
    for row in rows:
        as_of_date = cast(date, getattr(row, date_field_name))
        grouped.setdefault(as_of_date, []).append(row)
    return tuple((as_of_date, tuple(grouped[as_of_date])) for as_of_date in sorted(grouped))


def _row_to_record(row: ConnectorRow) -> dict[str, str | int]:
    payload = cast(dict[str, object], asdict(row))
    metadata = payload.pop("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("row metadata must serialize to a dictionary")
    metadata_payload = cast(dict[str, object], metadata)
    record: dict[str, str | int] = {
        "source_name": _normalize_scalar(metadata_payload["source_name"]),
        "source_series_id": _normalize_scalar(metadata_payload["source_series_id"]),
        "fetched_at": _normalize_scalar(metadata_payload["fetched_at"]),
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


class ConnectorRegistry(Protocol):
    def get_connector(self, source: str) -> object: ...


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


@final
class LiveConnectorRegistry:
    def get_connector(self, source: str) -> object:
        raise NotImplementedError(f"live connector not implemented for source: {source}")
