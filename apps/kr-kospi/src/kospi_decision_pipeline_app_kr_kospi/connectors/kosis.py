from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .base import ConnectorRowBase


@dataclass(frozen=True, slots=True)
class PerPbrPercentileRow(ConnectorRowBase):
    value_date: date
    per_percentile: Decimal
    pbr_percentile: Decimal


@dataclass(frozen=True, slots=True)
class KosisMacroIndicatorRow(ConnectorRowBase):
    value_date: date
    indicator_name: str
    indicator_value: Decimal
    unit: str


@runtime_checkable
class KosisConnector(Protocol):
    def fetch_per_pbr_percentiles(
        self, start: date, end: date
    ) -> tuple[PerPbrPercentileRow, ...]: ...

    def fetch_macro_indicators(
        self, start: date, end: date
    ) -> tuple[KosisMacroIndicatorRow, ...]: ...
