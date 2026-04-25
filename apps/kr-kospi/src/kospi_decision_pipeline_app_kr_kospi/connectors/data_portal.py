from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .base import ConnectorRow


@dataclass(frozen=True, slots=True)
class DataPortalSampleRow(ConnectorRow):
    value_date: date
    metric_name: str
    metric_value: Decimal


@runtime_checkable
class DataPortalConnector(Protocol):
    def fetch_sample_dataset(self, start: date, end: date) -> tuple[DataPortalSampleRow, ...]: ...
