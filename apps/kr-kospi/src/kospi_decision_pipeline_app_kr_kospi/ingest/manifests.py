from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import TypedDict, cast


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
    return BronzeManifest.from_dict(cast(BronzeManifestDict, cast(object, loaded)))
