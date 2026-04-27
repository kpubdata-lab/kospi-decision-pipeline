from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from kpubdata import Client
from kpubdata.core.models import Query

from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import (
    EcosBaseRateRow,
    EcosBondYieldRow,
    EcosUsdKrwRow,
    LiveEcosConnector,
    parse_base_rate_rows,
    parse_bond_yield_rows,
    parse_usd_krw_rows,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "ecos"
START_DATE = date(2024, 1, 2)
END_DATE = date(2024, 1, 4)


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


class _FakeClient:
    def __init__(self, provider_key: str, datasets: Mapping[str, _FakeDataset]) -> None:
        self._config = SimpleNamespace(provider_keys={"bok": provider_key})
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


def _load_payload(name: str) -> Mapping[str, object]:
    return cast(
        Mapping[str, object], json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    )


def _load_payload_dict(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8")))


def _records_from_payload(name: str) -> tuple[Mapping[str, object], ...]:
    payload = _load_payload(name)
    statistic_search = cast(Mapping[str, object], payload["StatisticSearch"])
    raw_rows = cast(list[Mapping[str, object]], statistic_search["row"])
    return tuple(raw_rows)


EcosRow = EcosBaseRateRow | EcosUsdKrwRow | EcosBondYieldRow


@pytest.mark.parametrize(
    ("fixture_name", "dataset_id", "fetcher_name", "value_attr", "expected_values"),
    [
        (
            "base_rate_statistic_search.json",
            "bok.base_rate",
            "fetch_base_rate_series",
            "base_rate",
            (Decimal("3.50"), Decimal("3.50"), Decimal("3.50")),
        ),
        (
            "usd_krw_statistic_search.json",
            "bok.usd_krw",
            "fetch_usd_krw_series",
            "exchange_rate",
            (Decimal("1293.10"), Decimal("1288.40"), Decimal("1290.00")),
        ),
        (
            "bond_yield_statistic_search.json",
            "bok.bond_yield_3y",
            "fetch_bond_yield_series",
            "yield_rate",
            (Decimal("3.23"), Decimal("3.20"), Decimal("3.18")),
        ),
    ],
)
def test_live_ecos_connector_fetches_series_via_kpubdata_client(
    fixture_name: str,
    dataset_id: str,
    fetcher_name: str,
    value_attr: str,
    expected_values: tuple[Decimal, ...],
) -> None:
    dataset = _FakeDataset(_records_from_payload(fixture_name))
    client = _FakeClient("test-api-key", {dataset_id: dataset})

    connector = LiveEcosConnector(client=cast(Client, client))

    rows = cast(tuple[EcosRow, ...], getattr(connector, fetcher_name)(START_DATE, END_DATE))

    assert client.dataset_calls == [dataset_id]
    assert dataset.queries == [
        Query(
            start_date=START_DATE.isoformat(),
            end_date=END_DATE.isoformat(),
            extra={"frequency": "D"},
        )
    ]
    assert tuple(getattr(row, value_attr) for row in rows) == expected_values
    assert tuple(row.value_date for row in rows) == (START_DATE, date(2024, 1, 3), END_DATE)
    assert rows[0].metadata.source_name == "ecos"
    assert rows[0].metadata.api_version == "StatisticSearch"
    assert (
        rows[0].metadata.key_fingerprint_sha256
        == hashlib.sha256("test-api-key".encode("utf-8")).hexdigest()[:16]
    )


def test_live_ecos_connector_falls_back_to_dataset_list_when_query_records_is_unavailable() -> None:
    dataset = _ListOnlyDataset(_records_from_payload("base_rate_statistic_search.json"))
    client = _ConfigurableClient("bok.base_rate", dataset, SimpleNamespace(provider_keys={}))

    connector = LiveEcosConnector(client=cast(Client, client))

    rows = connector.fetch_base_rate_series(START_DATE, END_DATE)

    assert rows
    assert dataset.calls == [
        {
            "start_date": START_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "frequency": "D",
        }
    ]


@pytest.mark.parametrize(
    "config",
    [
        None,
        SimpleNamespace(provider_keys="bad"),
        SimpleNamespace(provider_keys={1: "ignored", "bok": 1}),
    ],
)
def test_live_ecos_connector_leaves_fingerprint_empty_when_client_config_is_unusable(
    config: object | None,
) -> None:
    dataset = _FakeDataset(_records_from_payload("base_rate_statistic_search.json"))
    client = _ConfigurableClient("bok.base_rate", dataset, config)

    connector = LiveEcosConnector(client=cast(Client, client))

    rows = connector.fetch_base_rate_series(START_DATE, END_DATE)

    assert rows[0].metadata.key_fingerprint_sha256 is None


def test_live_ecos_connector_raises_when_dataset_cannot_query_records() -> None:
    client = _ConfigurableClient("bok.base_rate", object(), None)
    connector = LiveEcosConnector(client=cast(Client, client))

    with pytest.raises(TypeError, match="query_records"):
        connector.fetch_base_rate_series(START_DATE, END_DATE)


@pytest.mark.parametrize(
    ("fixture_name", "parser", "value_attr", "expected_values"),
    [
        (
            "base_rate_statistic_search.json",
            parse_base_rate_rows,
            "base_rate",
            (Decimal("3.50"), Decimal("3.50"), Decimal("3.50")),
        ),
        (
            "usd_krw_statistic_search.json",
            parse_usd_krw_rows,
            "exchange_rate",
            (Decimal("1293.10"), Decimal("1288.40"), Decimal("1290.00")),
        ),
        (
            "bond_yield_statistic_search.json",
            parse_bond_yield_rows,
            "yield_rate",
            (Decimal("3.23"), Decimal("3.20"), Decimal("3.18")),
        ),
    ],
)
def test_parse_ecos_rows_sorts_recorded_rows_deterministically(
    fixture_name: str,
    parser: Callable[[tuple[Mapping[str, object], ...], str, str], tuple[EcosRow, ...]],
    value_attr: str,
    expected_values: tuple[Decimal, ...],
) -> None:
    payload = _load_payload_dict(fixture_name)
    statistic_search = cast(dict[str, object], payload["StatisticSearch"])
    rows = cast(list[Mapping[str, object]], statistic_search["row"])

    parsed_rows = parser(
        tuple(reversed(rows)),
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert tuple(row.value_date for row in parsed_rows) == (START_DATE, date(2024, 1, 3), END_DATE)
    assert tuple(getattr(row, value_attr) for row in parsed_rows) == expected_values


@pytest.mark.parametrize(
    ("parser", "row_type"),
    [
        (parse_base_rate_rows, EcosBaseRateRow),
        (parse_usd_krw_rows, EcosUsdKrwRow),
        (parse_bond_yield_rows, EcosBondYieldRow),
    ],
)
def test_parse_ecos_rows_returns_empty_tuple_for_empty_record_batch(
    parser: Callable[[tuple[Mapping[str, object], ...], str, str], tuple[object, ...]],
    row_type: type[object],
) -> None:
    del row_type
    rows = parser((), "2024-01-15T00:00:00+00:00", "abc123def4567890")

    assert rows == ()


@pytest.mark.parametrize(
    ("parser", "bad_rows", "message"),
    [
        (parse_base_rate_rows, ({"DATA_VALUE": "3.50"},), "TIME"),
        (parse_usd_krw_rows, ({"TIME": "20240102"},), "DATA_VALUE"),
        (parse_bond_yield_rows, ({"TIME": 20240102, "DATA_VALUE": "3.20"},), "TIME"),
    ],
)
def test_parse_ecos_rows_validate_required_fields(
    parser: Callable[[tuple[Mapping[str, object], ...], str, str], tuple[object, ...]],
    bad_rows: tuple[Mapping[str, object], ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parser(bad_rows, "2024-01-15T00:00:00+00:00", "abc123def4567890")


@pytest.mark.parametrize(
    "payload",
    [{}, (1,)],
)
def test_parse_ecos_rows_validate_record_batch_shape(payload: object) -> None:
    with pytest.raises(ValueError):
        parse_base_rate_rows(payload, "2024-01-15T00:00:00+00:00", "abc123def4567890")
