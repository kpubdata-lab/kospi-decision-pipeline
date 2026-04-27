from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from types import SimpleNamespace
from typing import cast

import pytest
from kpubdata import Client
from kpubdata.core.models import Query
from kpubdata.exceptions import DatasetNotFoundError

from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import (
    LiveKosisConnector,
    UnsupportedDatasetError,
    parse_macro_indicator_rows,
)


START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 2, 29)
FETCHED_AT = datetime(2024, 3, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _FakeRecordBatch:
    items: tuple[Mapping[str, object], ...]


class _FakeDataset:
    def __init__(self, items: tuple[Mapping[str, object], ...]) -> None:
        self._batch = _FakeRecordBatch(items)
        self.queries: list[Query] = []

    def query_records(self, query: Query) -> _FakeRecordBatch:
        self.queries.append(query)
        return self._batch


class _ListOnlyDataset:
    def __init__(self, items: tuple[Mapping[str, object], ...]) -> None:
        self._batch = _FakeRecordBatch(items)
        self.calls: list[dict[str, object]] = []

    def list(self, **kwargs: object) -> _FakeRecordBatch:
        self.calls.append(dict(kwargs))
        return self._batch


class _DatasetNotFoundClient:
    def __init__(self) -> None:
        self._config = SimpleNamespace(provider_keys={"kosis": "test-kosis-key"})

    def dataset(self, dataset_id: str) -> _FakeDataset:
        raise DatasetNotFoundError(dataset_id)


class _FakeClient:
    def __init__(self, provider_key: str, datasets: Mapping[str, _FakeDataset]) -> None:
        self._config = SimpleNamespace(provider_keys={"kosis": provider_key})
        self._datasets = dict(datasets)
        self.dataset_calls: list[str] = []

    def dataset(self, dataset_id: str) -> _FakeDataset:
        self.dataset_calls.append(dataset_id)
        return self._datasets[dataset_id]


class _ConfigurableClient:
    def __init__(self, dataset_id: str, dataset: object, config: object | None) -> None:
        self._datasets = {dataset_id: dataset}
        if config is not None:
            self._config = config

    def dataset(self, dataset_id: str) -> object:
        return self._datasets[dataset_id]


def test_parse_macro_indicator_rows_parses_verified_monthly_kosis_payload() -> None:
    rows = parse_macro_indicator_rows(
        payload=(
            {
                "PRD_DE": "202402",
                "DT": "101.2",
                "C1_OBJ_NM": "반도체",
                "UNIT_NM": "2020=100",
            },
            {
                "PRD_DE": "202401",
                "DT": "100.1",
                "C1_OBJ_NM": "반도체",
                "UNIT_NM": "2020=100",
            },
        ),
        dataset_name="macro_indicators",
        fetched_at_utc=FETCHED_AT.isoformat(),
        key_fingerprint_sha256="fingerprint123456",
        series_name="반도체",
        unit="2020=100",
    )

    assert [row.value_date for row in rows] == [date(2024, 1, 1), date(2024, 2, 1)]
    assert [row.indicator_value for row in rows] == [Decimal("100.1"), Decimal("101.2")]
    assert all(row.indicator_name == "반도체" for row in rows)
    assert all(row.unit == "2020=100" for row in rows)
    assert rows[0].metadata.source_name == "kosis"
    assert rows[0].metadata.dataset_name == "macro_indicators"


def test_live_kosis_connector_fetches_macro_indicators_via_kpubdata_client() -> None:
    dataset = _FakeDataset(
        (
            {
                "PRD_DE": "202402",
                "DT": "101.2",
                "C1_OBJ_NM": "산업생산지수",
                "UNIT_NM": "2020=100",
            },
            {
                "PRD_DE": "202401",
                "DT": "100.1",
                "C1_OBJ_NM": "산업생산지수",
                "UNIT_NM": "2020=100",
            },
        )
    )
    client = _FakeClient("explicit-kosis-key", {"kosis.industrial_production": dataset})

    connector = LiveKosisConnector(client=cast(Client, client), now=lambda: FETCHED_AT)

    rows = connector.fetch_macro_indicators(START_DATE, END_DATE)

    assert client.dataset_calls == ["kosis.industrial_production"]
    assert dataset.queries == [
        Query(start_date=START_DATE.isoformat(), end_date=END_DATE.isoformat())
    ]
    assert [row.value_date for row in rows] == [date(2024, 1, 1), date(2024, 2, 1)]
    assert [row.indicator_value for row in rows] == [Decimal("100.1"), Decimal("101.2")]
    assert (
        rows[0].metadata.key_fingerprint_sha256
        == hashlib.sha256("explicit-kosis-key".encode("utf-8")).hexdigest()[:16]
    )


def test_live_kosis_connector_falls_back_to_dataset_list_when_query_records_is_unavailable() -> (
    None
):
    dataset = _ListOnlyDataset(
        (
            {
                "PRD_DE": "202401",
                "DT": "100.1",
                "C1_OBJ_NM": "산업생산지수",
                "UNIT_NM": "2020=100",
            },
        )
    )
    client = _ConfigurableClient(
        "kosis.industrial_production",
        dataset,
        SimpleNamespace(provider_keys={}),
    )

    connector = LiveKosisConnector(client=cast(Client, client), now=lambda: FETCHED_AT)

    rows = connector.fetch_macro_indicators(START_DATE, END_DATE)

    assert rows
    assert dataset.calls == [
        {
            "start_date": START_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
        }
    ]


def test_live_kosis_connector_rejects_unsupported_live_dataset_shape() -> None:
    connector = LiveKosisConnector(client=cast(Client, _FakeClient("test-kosis-key", {})))

    with pytest.raises(UnsupportedDatasetError, match="per_pbr_percentiles"):
        connector.fetch_per_pbr_percentiles(START_DATE, END_DATE)


def test_live_kosis_connector_translates_missing_kpubdata_dataset_to_existing_sentinel() -> None:
    connector = LiveKosisConnector(client=cast(Client, _DatasetNotFoundClient()))

    with pytest.raises(UnsupportedDatasetError, match="industrial_production"):
        connector.fetch_macro_indicators(START_DATE, END_DATE)


@pytest.mark.parametrize(
    "config",
    [
        None,
        SimpleNamespace(provider_keys="bad"),
        SimpleNamespace(provider_keys={1: "ignored", "kosis": 1}),
    ],
)
def test_live_kosis_connector_leaves_fingerprint_empty_when_client_config_is_unusable(
    config: object | None,
) -> None:
    dataset = _FakeDataset(({"PRD_DE": "202401", "DT": "100.1"},))
    client = _ConfigurableClient("kosis.industrial_production", dataset, config)

    connector = LiveKosisConnector(client=cast(Client, client), now=lambda: FETCHED_AT)

    rows = connector.fetch_macro_indicators(START_DATE, END_DATE)

    assert rows[0].metadata.key_fingerprint_sha256 is None


def test_live_kosis_connector_raises_when_dataset_cannot_query_records() -> None:
    client = _ConfigurableClient("kosis.industrial_production", object(), None)
    connector = LiveKosisConnector(client=cast(Client, client), now=lambda: FETCHED_AT)

    with pytest.raises(TypeError, match="query_records"):
        connector.fetch_macro_indicators(START_DATE, END_DATE)


def test_live_kosis_connector_uses_default_utc_clock() -> None:
    dataset = _FakeDataset(({"PRD_DE": "202401", "DT": "100.1"},))
    client = _FakeClient("explicit-kosis-key", {"kosis.industrial_production": dataset})
    connector = LiveKosisConnector(client=cast(Client, client))

    rows = connector.fetch_macro_indicators(START_DATE, END_DATE)

    assert rows[0].metadata.fetched_at_utc.endswith("+00:00")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "record batch payload"),
        (("bad-row",), "record payload"),
        (({"DT": "1.0"},), "PRD_DE"),
        (({"PRD_DE": 202401, "DT": "1.0"},), "PRD_DE"),
        (({"PRD_DE": "202401", "DT": 1.0},), "DT"),
        (({"PRD_DE": "202401", "DT": "1.0", "C1_OBJ_NM": 1},), "C1_OBJ_NM"),
        (({"PRD_DE": "202401", "DT": "1.0", "UNIT_NM": 1},), "UNIT_NM"),
        (({"PRD_DE": "2024", "DT": "1.0"},), "unsupported KOSIS period format"),
    ],
)
def test_parse_macro_indicator_rows_validates_payload_shape(payload: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_macro_indicator_rows(
            payload=payload,
            dataset_name="macro_indicators",
            fetched_at_utc=FETCHED_AT.isoformat(),
            key_fingerprint_sha256="fingerprint123456",
            series_name="verified-series",
            unit="index",
        )


def test_parse_macro_indicator_rows_uses_fallback_series_name_and_unit() -> None:
    rows = parse_macro_indicator_rows(
        payload=({"PRD_DE": "202401", "DT": "99.9"},),
        dataset_name="macro_indicators",
        fetched_at_utc=FETCHED_AT.isoformat(),
        key_fingerprint_sha256="fingerprint123456",
        series_name="verified-series",
        unit="index",
    )

    assert rows[0].indicator_name == "verified-series"
    assert rows[0].unit == "index"
