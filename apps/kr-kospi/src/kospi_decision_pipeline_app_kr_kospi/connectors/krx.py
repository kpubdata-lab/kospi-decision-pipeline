from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from .base import ConnectorRow


@dataclass(frozen=True, slots=True)
class KospiIndexRow(ConnectorRow):
    trade_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    turnover: Decimal


@dataclass(frozen=True, slots=True)
class InvestorFlowRow(ConnectorRow):
    trade_date: date
    individual_net_buy: Decimal
    foreign_net_buy: Decimal
    institution_net_buy: Decimal


@dataclass(frozen=True, slots=True)
class MarketValuationRow(ConnectorRow):
    trade_date: date
    market_capitalization: Decimal
    trailing_per: Decimal
    trailing_pbr: Decimal


@runtime_checkable
class KrxConnector(Protocol):
    def fetch_kospi_index(self, start: date, end: date) -> tuple[KospiIndexRow, ...]: ...

    def fetch_investor_flow(self, start: date, end: date) -> tuple[InvestorFlowRow, ...]: ...

    def fetch_market_valuation(self, start: date, end: date) -> tuple[MarketValuationRow, ...]: ...
