from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from kpubdata import Client

from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import LiveEcosConnector
from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import LiveKosisConnector
from kospi_decision_pipeline_app_kr_kospi.connectors.krx import PykrxKrxConnector


PARITY_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "parity" / "v0.2"
FETCHED_AT = datetime(2024, 2, 1, tzinfo=timezone.utc)
PARITY_API_KEY = "parity-api-key"


class _FakeRecordBatch:
    def __init__(self, items: tuple[Mapping[str, object], ...]) -> None:
        self.items = items


class _FakeDataset:
    def __init__(self, items: tuple[Mapping[str, object], ...]) -> None:
        self._batch = _FakeRecordBatch(items)

    def list(
        self,
        *,
        start_date: object,
        end_date: object,
        frequency: object | None = None,
        market: object | None = None,
    ) -> _FakeRecordBatch:
        del start_date, end_date, frequency, market
        return self._batch


class _FakeClient:
    def __init__(self, *, provider: str, datasets: Mapping[str, _FakeDataset]) -> None:
        self._config = SimpleNamespace(provider_keys={provider: PARITY_API_KEY})
        self._datasets = dict(datasets)

    def dataset(self, dataset_id: str) -> _FakeDataset:
        return self._datasets[dataset_id]


def _load_snapshot(name: str) -> dict[str, object]:
    return cast(
        dict[str, object], json.loads((PARITY_FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    )


def _load_window(snapshot: dict[str, object]) -> tuple[date, date]:
    window = cast(dict[str, str], snapshot["window"])
    return (date.fromisoformat(window["start"]), date.fromisoformat(window["end"]))


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _serialize(item) for key, item in cast(Mapping[object, object], value).items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_serialize(item) for item in cast(Sequence[object], value)]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _extract_ecos_records(payload: object) -> tuple[Mapping[str, object], ...]:
    mapping = cast(Mapping[str, object], payload)
    statistic_search = cast(Mapping[str, object], mapping["StatisticSearch"])
    return tuple(cast(list[Mapping[str, object]], statistic_search.get("row", [])))


def _krx_row_date(raw_row: Mapping[str, object]) -> str:
    return str(raw_row["index"])[:10]


def _extract_krx_kospi_items(snapshot: dict[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = cast(Mapping[str, object], snapshot["raw"])
    rows_payload = raw.get("ohlcv", raw)
    raw_rows = cast(list[Mapping[str, object]], cast(Mapping[str, object], rows_payload)["rows"])
    return tuple(
        {
            "date": _krx_row_date(raw_row),
            "open": cast(Mapping[str, object], raw_row["values"])["시가"],
            "high": cast(Mapping[str, object], raw_row["values"])["고가"],
            "low": cast(Mapping[str, object], raw_row["values"])["저가"],
            "close": cast(Mapping[str, object], raw_row["values"])["종가"],
            "volume": cast(Mapping[str, object], raw_row["values"])["거래량"],
            "trading_value": cast(Mapping[str, object], raw_row["values"])["거래대금"],
            "market_cap": cast(Mapping[str, object], raw_row["values"])["상장시가총액"],
        }
        for raw_row in raw_rows
    )


def _extract_krx_investor_items(snapshot: dict[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = cast(Mapping[str, object], snapshot["raw"])
    raw_rows = cast(list[Mapping[str, object]], raw["rows"])
    labels = (
        ("개인", "개인"),
        ("외국인합계", "외국인"),
        ("기관합계", "기관"),
    )
    return tuple(
        {
            "date": _krx_row_date(raw_row),
            "market": "KOSPI",
            "investor_type": investor_type,
            "net_value": cast(Mapping[str, object], raw_row["values"])[column_name],
        }
        for raw_row in raw_rows
        for column_name, investor_type in labels
    )


def _extract_krx_market_valuation_items(
    snapshot: dict[str, object],
) -> tuple[Mapping[str, object], ...]:
    raw = cast(Mapping[str, object], snapshot["raw"])
    fundamental = cast(Mapping[str, object], raw["fundamental"])
    raw_rows = cast(list[Mapping[str, object]], fundamental["rows"])
    return tuple(
        {
            "date": _krx_row_date(raw_row),
            "market": "KOSPI",
            "per": cast(Mapping[str, object], raw_row["values"])["PER"],
            "pbr": cast(Mapping[str, object], raw_row["values"])["PBR"],
        }
        for raw_row in raw_rows
    )


def _fetch_ecos_rows(snapshot_name: str, fetcher_name: str) -> list[object]:
    snapshot = _load_snapshot(snapshot_name)
    start, end = _load_window(snapshot)
    dataset_name = {
        "fetch_base_rate_series": "bok.base_rate",
        "fetch_usd_krw_series": "bok.usd_krw",
        "fetch_bond_yield_series": "bok.bond_yield_3y",
    }[fetcher_name]
    client = _FakeClient(
        provider="bok",
        datasets={dataset_name: _FakeDataset(_extract_ecos_records(snapshot["raw"]))},
    )
    connector = LiveEcosConnector(
        client=cast(Client, client),
        now=lambda: FETCHED_AT,
    )
    return cast(list[object], list(getattr(connector, fetcher_name)(start, end)))


def _fetch_kosis_rows(snapshot_name: str) -> list[object]:
    snapshot = _load_snapshot(snapshot_name)
    start, end = _load_window(snapshot)
    payload = tuple(cast(list[Mapping[str, object]], snapshot["raw"]))
    client = _FakeClient(
        provider="kosis",
        datasets={"kosis.industrial_production": _FakeDataset(payload)},
    )
    connector = LiveKosisConnector(
        client=cast(Client, client),
        now=lambda: FETCHED_AT,
    )
    return list(connector.fetch_macro_indicators(start, end))


def _fetch_krx_rows(snapshot_name: str, fetcher_name: str) -> list[object]:
    snapshot = _load_snapshot(snapshot_name)
    start, end = _load_window(snapshot)
    datasets: dict[str, _FakeDataset] = {
        "krx.kospi_index": _FakeDataset(()),
        "krx.investor_flow": _FakeDataset(()),
        "krx.market_valuation": _FakeDataset(()),
    }
    if fetcher_name == "fetch_kospi_index":
        datasets["krx.kospi_index"] = _FakeDataset(_extract_krx_kospi_items(snapshot))
    elif fetcher_name == "fetch_investor_flow":
        datasets["krx.investor_flow"] = _FakeDataset(_extract_krx_investor_items(snapshot))
    else:
        datasets["krx.kospi_index"] = _FakeDataset(_extract_krx_kospi_items(snapshot))
        datasets["krx.market_valuation"] = _FakeDataset(
            _extract_krx_market_valuation_items(snapshot)
        )
    client = _FakeClient(
        provider="krx",
        datasets=datasets,
    )
    connector = PykrxKrxConnector(client=cast(Client, client), clock=lambda: FETCHED_AT)
    return cast(list[object], list(getattr(connector, fetcher_name)(start, end)))


@pytest.mark.parametrize(
    ("snapshot_name", "fetcher_name"),
    [
        ("ecos_base_rate.json", "fetch_base_rate_series"),
        ("ecos_usd_krw.json", "fetch_usd_krw_series"),
        ("ecos_bond_yield_3y.json", "fetch_bond_yield_series"),
    ],
)
def test_v02_ecos_parity_snapshots_match_live_connector_normalization(
    snapshot_name: str,
    fetcher_name: str,
) -> None:
    snapshot = _load_snapshot(snapshot_name)

    assert _serialize(_fetch_ecos_rows(snapshot_name, fetcher_name)) == snapshot["normalized"]


@pytest.mark.parametrize(
    ("snapshot_name", "fetcher_name"),
    [
        ("krx_kospi_index_ohlcv.json", "fetch_kospi_index"),
        ("krx_investor_flow.json", "fetch_investor_flow"),
        ("krx_market_valuation.json", "fetch_market_valuation"),
    ],
)
def test_v02_krx_parity_snapshots_match_live_connector_normalization(
    snapshot_name: str,
    fetcher_name: str,
) -> None:
    snapshot = _load_snapshot(snapshot_name)

    assert _serialize(_fetch_krx_rows(snapshot_name, fetcher_name)) == snapshot["normalized"]


def test_v02_kosis_parity_snapshot_matches_live_connector_normalization() -> None:
    snapshot = _load_snapshot("kosis_industrial_production.json")

    assert (
        _serialize(_fetch_kosis_rows("kosis_industrial_production.json")) == snapshot["normalized"]
    )
