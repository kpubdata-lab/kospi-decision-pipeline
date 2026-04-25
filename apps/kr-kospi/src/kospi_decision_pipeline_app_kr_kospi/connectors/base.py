from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_name: str
    source_series_id: str
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class ConnectorRow:
    metadata: SourceMetadata


@runtime_checkable
class Connector(Protocol):
    pass
