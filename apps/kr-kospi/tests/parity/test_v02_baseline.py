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

    def query_records(self, query: object) -> _FakeRecordBatch:
        del query
        return self._batch


class _FakeClient:
    def __init__(self, *, provider: str, datasets: Mapping[str, _FakeDataset]) -> None:
        self._config = SimpleNamespace(provider_keys={provider: PARITY_API_KEY})
        self._datasets = dict(datasets)

    def dataset(self, dataset_id: str) -> _FakeDataset:
        return self._datasets[dataset_id]


class _FakeFrameIndex:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def tolist(self) -> list[object]:
        return list(self._values)


class _FakeFrameAtAccessor:
    def __init__(self, rows: dict[object, dict[str, object]]) -> None:
        self._rows = rows

    def __getitem__(self, key: tuple[object, str]) -> object:
        index_value, column_name = key
        return self._rows[index_value][column_name]


class _FakeDataFrame:
    def __init__(self, rows: dict[object, dict[str, object]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    @property
    def index(self) -> _FakeFrameIndex:
        return _FakeFrameIndex(tuple(self._rows))

    @property
    def at(self) -> _FakeFrameAtAccessor:
        return _FakeFrameAtAccessor(self._rows)

    def sort_index(self) -> _FakeDataFrame:
        return _FakeDataFrame(dict(sorted(self._rows.items(), key=lambda item: str(item[0]))))


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


def _frame_from_payload(payload: object) -> _FakeDataFrame:
    mapping = cast(dict[str, object], payload)
    raw_rows = cast(list[dict[str, object]], mapping["rows"])
    rows: dict[object, dict[str, object]] = {}
    for raw_row in raw_rows:
        rows[datetime.fromisoformat(str(raw_row["index"]))] = cast(
            dict[str, object], raw_row["values"]
        )
    return _FakeDataFrame(rows)


def _extract_ohlcv_payload(payload: object) -> object:
    if isinstance(payload, Mapping):
        mapping = cast(Mapping[str, object], payload)
        ohlcv_payload = mapping.get("ohlcv")
        if ohlcv_payload is not None:
            return ohlcv_payload
        return dict(mapping)
    return payload


def _extract_ecos_records(payload: object) -> tuple[Mapping[str, object], ...]:
    mapping = cast(Mapping[str, object], payload)
    statistic_search = cast(Mapping[str, object], mapping["StatisticSearch"])
    return tuple(cast(list[Mapping[str, object]], statistic_search.get("row", [])))


class _ParityPykrxStockApi:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def get_index_ohlcv_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        freq: str = "d",
        name_display: bool = True,
    ) -> _FakeDataFrame:
        del fromdate, todate, ticker, freq, name_display
        return _frame_from_payload(_extract_ohlcv_payload(self._payload["raw"]))

    def get_market_trading_value_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        etf: bool = False,
        etn: bool = False,
        elw: bool = False,
        on: str = "순매수",
        detail: bool = False,
        freq: str = "d",
    ) -> _FakeDataFrame:
        del fromdate, todate, ticker, etf, etn, elw, on, detail, freq
        return _frame_from_payload(self._payload["raw"])

    def get_index_fundamental_by_date(
        self,
        fromdate: str,
        todate: str,
        ticker: str,
        prev: bool = True,
    ) -> _FakeDataFrame:
        del fromdate, todate, ticker, prev
        raw = cast(dict[str, object], self._payload["raw"])
        return _frame_from_payload(raw["fundamental"])


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
    connector = PykrxKrxConnector(
        stock_api=_ParityPykrxStockApi(snapshot),
        clock=lambda: FETCHED_AT,
    )
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
def test_v02_krx_parity_snapshots_match_pykrx_connector_normalization(
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
