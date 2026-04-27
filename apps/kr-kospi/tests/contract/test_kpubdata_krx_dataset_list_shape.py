from __future__ import annotations

from dataclasses import dataclass
import inspect

import pytest
from kpubdata import Client
from kpubdata.providers.krx import adapter as krx_adapter


@dataclass(frozen=True, slots=True)
class _FakeRecordBatch:
    items: tuple[object, ...]
    total_count: int | None = 0
    next_page: int | None = None
    next_cursor: str | None = None


@pytest.mark.parametrize(
    "dataset_id",
    [
        "krx.kospi_index",
        "krx.investor_flow",
        "krx.market_valuation",
    ],
)
def test_krx_dataset_list_signature_accepts_top_level_kwargs(dataset_id: str) -> None:
    signature = inspect.signature(Client.from_env().dataset(dataset_id).list)

    assert len(signature.parameters) == 1
    assert next(iter(signature.parameters.values())).kind is inspect.Parameter.VAR_KEYWORD


@pytest.mark.parametrize(
    "dataset_id",
    [
        "krx.kospi_index",
        "krx.investor_flow",
        "krx.market_valuation",
    ],
)
def test_krx_dataset_list_maps_top_level_kwargs_into_query(
    monkeypatch: pytest.MonkeyPatch,
    dataset_id: str,
) -> None:
    monkeypatch.setenv("KPUBDATA_KRX_INTEGRATION", "1")
    captured_queries: list[object] = []

    def spy(self: object, dataset_ref: object, query: object) -> _FakeRecordBatch:
        del self, dataset_ref
        captured_queries.append(query)
        return _FakeRecordBatch(())

    monkeypatch.setattr(krx_adapter.KrxAdapter, "query_records", spy)

    batch = (
        Client.from_env()
        .dataset(dataset_id)
        .list(
            start_date="2024-01-02",
            end_date="2024-01-05",
        )
    )

    assert tuple(batch.items) == ()
    assert len(captured_queries) == 1
    query = captured_queries[0]
    assert getattr(query, "start_date") == "2024-01-02"
    assert getattr(query, "end_date") == "2024-01-05"
    assert getattr(query, "filters") == {}
    assert getattr(query, "extra") == {}
