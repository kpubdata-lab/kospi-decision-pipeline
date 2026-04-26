from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable


def _parse_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("fetched_at_utc must be an ISO-8601 UTC timestamp")
    return parsed


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_name: str
    dataset_name: str
    fetched_at_utc: str
    connector_id: str
    api_version: str | None = None
    key_fingerprint_sha256: str | None = None

    def __post_init__(self) -> None:
        _ = _parse_utc_timestamp(self.fetched_at_utc)

    @property
    def source_series_id(self) -> str:
        return self.dataset_name

    @property
    def fetched_at(self) -> datetime:
        return _parse_utc_timestamp(self.fetched_at_utc)


@dataclass(frozen=True, slots=True)
class ConnectorRowBase:
    metadata: SourceMetadata


@runtime_checkable
class ConnectorRow(Protocol):
    @property
    def metadata(self) -> SourceMetadata: ...


@runtime_checkable
class Connector(Protocol):
    pass
