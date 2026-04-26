from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import TypedDict, cast, override

from ..connectors.base import SourceMetadata


class ManifestEntryDict(TypedDict):
    path: str
    sha256: str
    row_count: int
    fetched_at: str


class BronzeManifestDict(TypedDict):
    dataset_id: str
    source_name: str
    run_timestamp: str
    entries: list[ManifestEntryDict]


class SourceMetadataDict(TypedDict):
    source_name: str
    dataset_name: str
    fetched_at_utc: str
    connector_id: str
    api_version: str | None
    key_fingerprint_sha256: str | None


class LiveIngestManifestDict(BronzeManifestDict):
    snapshot_id: str
    requested_start: str
    requested_end: str
    written_dates: list[str]
    skipped_dates: list[str]
    failed_dates: list[str]
    source_metadata: SourceMetadataDict


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: Path
    sha256: str
    row_count: int
    fetched_at: str

    def to_dict(self) -> ManifestEntryDict:
        return {
            "path": self.path.as_posix(),
            "sha256": self.sha256,
            "row_count": self.row_count,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, payload: ManifestEntryDict) -> ManifestEntry:
        return cls(
            path=Path(payload["path"]),
            sha256=payload["sha256"],
            row_count=payload["row_count"],
            fetched_at=payload["fetched_at"],
        )


@dataclass(frozen=True, slots=True)
class BronzeManifest:
    dataset_id: str
    source_name: str
    run_timestamp: datetime
    entries: tuple[ManifestEntry, ...]

    def to_dict(self) -> BronzeManifestDict:
        return {
            "dataset_id": self.dataset_id,
            "source_name": self.source_name,
            "run_timestamp": self.run_timestamp.isoformat(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    def to_deterministic_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "source_name": self.source_name,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload: BronzeManifestDict) -> BronzeManifest:
        return cls(
            dataset_id=payload["dataset_id"],
            source_name=payload["source_name"],
            run_timestamp=datetime.fromisoformat(payload["run_timestamp"]),
            entries=tuple(ManifestEntry.from_dict(raw_entry) for raw_entry in payload["entries"]),
        )


@dataclass(frozen=True, slots=True)
class LiveIngestManifest(BronzeManifest):
    snapshot_id: str
    requested_start: date
    requested_end: date
    written_dates: tuple[date, ...]
    skipped_dates: tuple[date, ...]
    failed_dates: tuple[date, ...]
    source_metadata: SourceMetadata

    @override
    def to_dict(self) -> LiveIngestManifestDict:
        payload = super(LiveIngestManifest, self).to_dict()
        return {
            **payload,
            "snapshot_id": self.snapshot_id,
            "requested_start": self.requested_start.isoformat(),
            "requested_end": self.requested_end.isoformat(),
            "written_dates": [value.isoformat() for value in self.written_dates],
            "skipped_dates": [value.isoformat() for value in self.skipped_dates],
            "failed_dates": [value.isoformat() for value in self.failed_dates],
            "source_metadata": _source_metadata_to_dict(self.source_metadata),
        }

    @override
    def to_deterministic_dict(self) -> dict[str, object]:
        payload = super(LiveIngestManifest, self).to_deterministic_dict()
        payload.update(
            {
                "snapshot_id": self.snapshot_id,
                "requested_start": self.requested_start.isoformat(),
                "requested_end": self.requested_end.isoformat(),
                "written_dates": [value.isoformat() for value in self.written_dates],
                "skipped_dates": [value.isoformat() for value in self.skipped_dates],
                "failed_dates": [value.isoformat() for value in self.failed_dates],
                "source_metadata": _source_metadata_to_dict(self.source_metadata),
            }
        )
        return payload


def _source_metadata_to_dict(metadata: SourceMetadata) -> SourceMetadataDict:
    return {
        "source_name": metadata.source_name,
        "dataset_name": metadata.dataset_name,
        "fetched_at_utc": metadata.fetched_at_utc,
        "connector_id": metadata.connector_id,
        "api_version": metadata.api_version,
        "key_fingerprint_sha256": metadata.key_fingerprint_sha256,
    }


def _source_metadata_from_dict(payload: SourceMetadataDict) -> SourceMetadata:
    return SourceMetadata(
        source_name=payload["source_name"],
        dataset_name=payload["dataset_name"],
        fetched_at_utc=payload["fetched_at_utc"],
        connector_id=payload["connector_id"],
        api_version=payload["api_version"],
        key_fingerprint_sha256=payload["key_fingerprint_sha256"],
    )


def _live_manifest_from_dict(payload: LiveIngestManifestDict) -> LiveIngestManifest:
    return LiveIngestManifest(
        dataset_id=payload["dataset_id"],
        source_name=payload["source_name"],
        run_timestamp=datetime.fromisoformat(payload["run_timestamp"]),
        entries=tuple(ManifestEntry.from_dict(raw_entry) for raw_entry in payload["entries"]),
        snapshot_id=payload["snapshot_id"],
        requested_start=date.fromisoformat(payload["requested_start"]),
        requested_end=date.fromisoformat(payload["requested_end"]),
        written_dates=tuple(date.fromisoformat(value) for value in payload["written_dates"]),
        skipped_dates=tuple(date.fromisoformat(value) for value in payload["skipped_dates"]),
        failed_dates=tuple(date.fromisoformat(value) for value in payload["failed_dates"]),
        source_metadata=_source_metadata_from_dict(payload["source_metadata"]),
    )


def write_manifest(path: Path, manifest: BronzeManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_manifest(path: Path) -> BronzeManifest:
    loaded = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(loaded, dict):
        raise ValueError("manifest payload must be an object")
    if "snapshot_id" in loaded:
        return _live_manifest_from_dict(cast(LiveIngestManifestDict, cast(object, loaded)))
    return BronzeManifest.from_dict(cast(BronzeManifestDict, cast(object, loaded)))
