from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .base import ConnectorRowBase


@dataclass(frozen=True, slots=True)
class EcosBaseRateRow(ConnectorRowBase):
    value_date: date
    base_rate: Decimal


@dataclass(frozen=True, slots=True)
class EcosUsdKrwRow(ConnectorRowBase):
    value_date: date
    exchange_rate: Decimal


@dataclass(frozen=True, slots=True)
class EcosBondYieldRow(ConnectorRowBase):
    value_date: date
    maturity_code: str
    yield_rate: Decimal


@runtime_checkable
class EcosConnector(Protocol):
    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]: ...

    def fetch_usd_krw_series(self, start: date, end: date) -> tuple[EcosUsdKrwRow, ...]: ...

    def fetch_bond_yield_series(self, start: date, end: date) -> tuple[EcosBondYieldRow, ...]: ...
