from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from kpubdata import Client

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import (
    InvestorFlowRow,
    KospiIndexRow,
    MarketValuationRow,
    PykrxKrxConnector,
)


START_DATE = date(2024, 1, 2)
END_DATE = date(2024, 1, 3)
FETCHED_AT = datetime(2024, 1, 10, 9, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _FakeRecordBatch:
    items: tuple[Mapping[str, object], ...]


class _FakeDataset:
    def __init__(self, items: tuple[Mapping[str, object], ...]) -> None:
        self._batch = _FakeRecordBatch(items)
        self.calls: list[dict[str, object]] = []

    def list(
        self,
        *,
        start_date: object,
        end_date: object,
        market: object | None = None,
    ) -> _FakeRecordBatch:
        self.calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "market": market,
            }
        )
        return self._batch


class _FakeClient:
    def __init__(self, datasets: Mapping[str, object]) -> None:
        self._config = SimpleNamespace(provider_keys={})
        self._datasets = dict(datasets)
        self.dataset_calls: list[str] = []

    def dataset(self, dataset_id: str) -> object:
        self.dataset_calls.append(dataset_id)
        return self._datasets[dataset_id]


class _ConfigurableClient:
    def __init__(self, dataset_id: str, dataset: object) -> None:
        self._datasets = {dataset_id: dataset}

    def dataset(self, dataset_id: str) -> object:
        return self._datasets[dataset_id]


def _build_client(**datasets: object) -> _FakeClient:
    return _FakeClient(datasets)


def test_live_krx_connector_normalizes_kpubdata_record_batches_into_typed_rows() -> None:
    kospi_dataset = _FakeDataset(
        (
            {
                "date": "2024-01-03",
                "open": "2660.0",
                "high": "2672.1",
                "low": "2631.5",
                "close": "2645.2",
                "volume": 460000000,
                "trading_value": "9100000000000",
                "market_cap": "2100000000000000",
            },
            {
                "date": "2024-01-02",
                "open": "2640.5",
                "high": "2655.0",
                "low": "2621.0",
                "close": "2651.8",
                "volume": 470000000,
                "trading_value": "9200000000000",
                "market_cap": "2110000000000000",
            },
        )
    )
    investor_dataset = _FakeDataset(
        (
            {"date": "2024-01-03", "investor_type": "외국인", "net_value": "150000000000"},
            {"date": "2024-01-02", "investor_type": "기관", "net_value": "20000000000"},
            {"date": "2024-01-02", "investor_type": "외국인", "net_value": "-120000000000"},
            {"date": "2024-01-03", "investor_type": "개인", "net_value": "-200000000000"},
            {"date": "2024-01-03", "investor_type": "기관", "net_value": "50000000000"},
            {"date": "2024-01-02", "investor_type": "개인", "net_value": "100000000000"},
        )
    )
    valuation_dataset = _FakeDataset(
        (
            {"date": "2024-01-03", "per": "12.5", "pbr": "0.95"},
            {"date": "2024-01-02", "per": "12.2", "pbr": "0.93"},
        )
    )
    client = _build_client(
        **{
            "krx.kospi_index": kospi_dataset,
            "krx.investor_flow": investor_dataset,
            "krx.market_valuation": valuation_dataset,
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client), clock=lambda: FETCHED_AT)

    kospi_rows = connector.fetch_kospi_index(START_DATE, END_DATE)
    investor_rows = connector.fetch_investor_flow(START_DATE, END_DATE)
    valuation_rows = connector.fetch_market_valuation(START_DATE, END_DATE)

    assert kospi_rows == (
        KospiIndexRow(
            metadata=kospi_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            open_price=Decimal("2640.5"),
            high_price=Decimal("2655.0"),
            low_price=Decimal("2621.0"),
            close_price=Decimal("2651.8"),
            volume=470000000,
            turnover=Decimal("9200000000000"),
        ),
        KospiIndexRow(
            metadata=kospi_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            open_price=Decimal("2660.0"),
            high_price=Decimal("2672.1"),
            low_price=Decimal("2631.5"),
            close_price=Decimal("2645.2"),
            volume=460000000,
            turnover=Decimal("9100000000000"),
        ),
    )
    assert investor_rows == (
        InvestorFlowRow(
            metadata=investor_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            individual_net_buy=Decimal("100000000000"),
            foreign_net_buy=Decimal("-120000000000"),
            institution_net_buy=Decimal("20000000000"),
        ),
        InvestorFlowRow(
            metadata=investor_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            individual_net_buy=Decimal("-200000000000"),
            foreign_net_buy=Decimal("150000000000"),
            institution_net_buy=Decimal("50000000000"),
        ),
    )
    assert valuation_rows == (
        MarketValuationRow(
            metadata=valuation_rows[0].metadata,
            trade_date=date(2024, 1, 2),
            market_capitalization=Decimal("2110000000000000"),
            trailing_per=Decimal("12.2"),
            trailing_pbr=Decimal("0.93"),
        ),
        MarketValuationRow(
            metadata=valuation_rows[0].metadata,
            trade_date=date(2024, 1, 3),
            market_capitalization=Decimal("2100000000000000"),
            trailing_per=Decimal("12.5"),
            trailing_pbr=Decimal("0.95"),
        ),
    )
    assert kospi_rows[0].metadata.source_name == "krx"
    assert kospi_rows[0].metadata.dataset_name == "kospi_index"
    assert kospi_rows[0].metadata.connector_id.endswith("PykrxKrxConnector")
    assert kospi_rows[0].metadata.fetched_at_utc == FETCHED_AT.isoformat()
    assert investor_rows[0].metadata.dataset_name == "investor_flow"
    assert valuation_rows[0].metadata.dataset_name == "market_valuation"
    assert client.dataset_calls == [
        "krx.kospi_index",
        "krx.investor_flow",
        "krx.market_valuation",
        "krx.kospi_index",
    ]
    assert kospi_dataset.calls == [
        {"start_date": START_DATE.isoformat(), "end_date": END_DATE.isoformat(), "market": None},
        {"start_date": START_DATE.isoformat(), "end_date": END_DATE.isoformat(), "market": None},
    ]
    assert investor_dataset.calls == [
        {"start_date": START_DATE.isoformat(), "end_date": END_DATE.isoformat(), "market": None}
    ]
    assert valuation_dataset.calls == [
        {"start_date": START_DATE.isoformat(), "end_date": END_DATE.isoformat(), "market": None}
    ]


def test_live_krx_connector_returns_empty_rows_for_empty_record_batches() -> None:
    empty_dataset = _FakeDataset(())
    client = _build_client(
        **{
            "krx.kospi_index": empty_dataset,
            "krx.investor_flow": empty_dataset,
            "krx.market_valuation": empty_dataset,
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    assert connector.fetch_kospi_index(date(2024, 1, 6), date(2024, 1, 7)) == ()
    assert connector.fetch_investor_flow(date(2024, 1, 6), date(2024, 1, 7)) == ()
    assert connector.fetch_market_valuation(date(2024, 1, 6), date(2024, 1, 7)) == ()


def test_live_krx_connector_joins_market_caps_with_market_valuation_rows_by_trade_date() -> None:
    kospi_dataset = _FakeDataset(
        (
            {"date": "2024-01-04", "market_cap": "999"},
            {"date": "2024-01-02", "market_cap": "2110000000000000"},
            {"date": "2024-01-03", "market_cap": "2100000000000000"},
        )
    )
    valuation_dataset = _FakeDataset(
        (
            {"date": "2024-01-03", "per": "12.5", "pbr": "0.95"},
            {"date": "2024-01-02", "per": "12.2", "pbr": "0.93"},
        )
    )
    client = _build_client(
        **{
            "krx.kospi_index": kospi_dataset,
            "krx.investor_flow": _FakeDataset(()),
            "krx.market_valuation": valuation_dataset,
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client), clock=lambda: FETCHED_AT)

    rows = connector.fetch_market_valuation(START_DATE, END_DATE)

    assert [(row.trade_date, row.market_capitalization) for row in rows] == [
        (date(2024, 1, 2), Decimal("2110000000000000")),
        (date(2024, 1, 3), Decimal("2100000000000000")),
    ]


def test_live_krx_connector_rejects_invalid_decimal_values() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(
                (
                    {
                        "date": "2024-01-02",
                        "open": "bad-decimal",
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                        "trading_value": 1,
                        "market_cap": 1,
                    },
                )
            ),
            "krx.investor_flow": _FakeDataset(()),
            "krx.market_valuation": _FakeDataset(()),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    with pytest.raises(ValueError, match="invalid decimal value"):
        connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 2))


def test_live_krx_connector_rejects_non_finite_decimal_values() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(({"date": "2024-01-02", "market_cap": 1},)),
            "krx.investor_flow": _FakeDataset(()),
            "krx.market_valuation": _FakeDataset(
                ({"date": "2024-01-02", "per": "NaN", "pbr": "0.93"},)
            ),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    with pytest.raises(ValueError, match="non-finite decimal value"):
        connector.fetch_market_valuation(date(2024, 1, 2), date(2024, 1, 2))


def test_live_krx_connector_rejects_unsupported_row_dates() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(
                (
                    {
                        "date": cast(object, object()),
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                        "trading_value": 1,
                        "market_cap": 1,
                    },
                )
            ),
            "krx.investor_flow": _FakeDataset(()),
            "krx.market_valuation": _FakeDataset(()),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    with pytest.raises(ValueError, match="unsupported row date value"):
        connector.fetch_kospi_index(date(2024, 1, 2), date(2024, 1, 2))


def test_live_krx_connector_accepts_native_date_values() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(()),
            "krx.investor_flow": _FakeDataset(
                ({"date": date(2024, 1, 2), "investor_type": "개인", "net_value": Decimal("1")},)
            ),
            "krx.market_valuation": _FakeDataset(()),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 2))

    assert rows[0].trade_date == date(2024, 1, 2)


def test_live_krx_connector_accepts_string_datetime_values() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(()),
            "krx.investor_flow": _FakeDataset(
                (
                    {
                        "date": "2024-01-02 00:00:00",
                        "investor_type": "개인",
                        "net_value": Decimal("1"),
                    },
                )
            ),
            "krx.market_valuation": _FakeDataset(()),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    rows = connector.fetch_investor_flow(date(2024, 1, 2), date(2024, 1, 2))

    assert rows[0].trade_date == date(2024, 1, 2)


def test_live_krx_connector_sorts_rows_deterministically() -> None:
    client = _build_client(
        **{
            "krx.kospi_index": _FakeDataset(
                (
                    {
                        "date": "2024-01-03",
                        "open": 2,
                        "high": 2,
                        "low": 2,
                        "close": 2,
                        "volume": 2,
                        "trading_value": 2,
                        "market_cap": 20,
                    },
                    {
                        "date": "2024-01-02",
                        "open": 1,
                        "high": 1,
                        "low": 1,
                        "close": 1,
                        "volume": 1,
                        "trading_value": 1,
                        "market_cap": 10,
                    },
                )
            ),
            "krx.investor_flow": _FakeDataset(
                (
                    {"date": "2024-01-03", "investor_type": "개인", "net_value": 2},
                    {"date": "2024-01-02", "investor_type": "개인", "net_value": 1},
                )
            ),
            "krx.market_valuation": _FakeDataset(
                (
                    {"date": "2024-01-03", "per": 2, "pbr": 2},
                    {"date": "2024-01-02", "per": 1, "pbr": 1},
                )
            ),
        }
    )
    connector = PykrxKrxConnector(client=cast(Client, client))

    kospi_rows = connector.fetch_kospi_index(START_DATE, END_DATE)
    investor_rows = connector.fetch_investor_flow(START_DATE, END_DATE)
    valuation_rows = connector.fetch_market_valuation(START_DATE, END_DATE)

    assert tuple(row.trade_date for row in kospi_rows) == (date(2024, 1, 2), date(2024, 1, 3))
    assert tuple(row.trade_date for row in investor_rows) == (date(2024, 1, 2), date(2024, 1, 3))
    assert tuple(row.trade_date for row in valuation_rows) == (date(2024, 1, 2), date(2024, 1, 3))


def test_live_krx_connector_raises_when_dataset_cannot_list_records() -> None:
    client = _ConfigurableClient("krx.kospi_index", object())
    connector = PykrxKrxConnector(client=cast(Client, client))

    with pytest.raises(AttributeError, match="list"):
        connector.fetch_kospi_index(START_DATE, END_DATE)
