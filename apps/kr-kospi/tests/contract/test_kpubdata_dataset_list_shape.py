from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from kpubdata import Client
from kpubdata.providers.bok import adapter as bok_adapter
from kpubdata.providers.kosis import adapter as kosis_adapter


@dataclass(frozen=True, slots=True)
class _FakeRecordBatch:
    items: Sequence[object]
    total_count: int | None = 0
    next_page: int | None = None
    next_cursor: str | None = None


def test_bok_dataset_list_maps_top_level_kwargs_into_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "test-bok-api-key")
    captured_queries: list[object] = []

    def spy(self: object, dataset_ref: object, query: object) -> _FakeRecordBatch:
        del self, dataset_ref
        captured_queries.append(query)
        return _FakeRecordBatch(())

    monkeypatch.setattr(bok_adapter.BokAdapter, "query_records", spy)

    client = Client.from_env()
    batch = client.dataset("bok.base_rate").list(
        start_date="2024-01-01",
        end_date="2024-01-31",
        frequency="D",
    )

    assert tuple(batch.items) == ()
    assert len(captured_queries) == 1
    query = captured_queries[0]
    assert getattr(query, "start_date") == "2024-01-01"
    assert getattr(query, "end_date") == "2024-01-31"
    assert getattr(query, "filters") == {"frequency": "D"}
    assert getattr(query, "extra") == {}


def test_kosis_dataset_list_maps_top_level_kwargs_into_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KPUBDATA_KOSIS_API_KEY", "test-kosis-api-key")
    captured_queries: list[object] = []

    def spy(self: object, dataset_ref: object, query: object) -> _FakeRecordBatch:
        del self, dataset_ref
        captured_queries.append(query)
        return _FakeRecordBatch(())

    monkeypatch.setattr(kosis_adapter.KosisAdapter, "query_records", spy)

    client = Client.from_env()
    batch = client.dataset("kosis.industrial_production").list(
        start_date="2024-01-01",
        end_date="2024-03-31",
    )

    assert tuple(batch.items) == ()
    assert len(captured_queries) == 1
    query = captured_queries[0]
    assert getattr(query, "start_date") == "2024-01-01"
    assert getattr(query, "end_date") == "2024-03-31"
    assert getattr(query, "filters") == {}
    assert getattr(query, "extra") == {}
