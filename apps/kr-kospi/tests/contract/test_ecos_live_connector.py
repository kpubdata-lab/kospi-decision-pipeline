from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import httpx
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import (
    LiveEcosConnector,
    parse_base_rate_rows,
    parse_bond_yield_rows,
    parse_usd_krw_rows,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "ecos"
START_DATE = date(2024, 1, 2)
END_DATE = date(2024, 1, 4)
BASE_RATE_PATH = (
    "/api/StatisticSearch/test-api-key/json/kr/1/100000/722Y001/D/20240102/20240104/0101000"
)
USD_KRW_PATH = (
    "/api/StatisticSearch/test-api-key/json/kr/1/100000/731Y003/D/20240102/20240104/0000003"
)


def _load_payload(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))


def _json_response(request: httpx.Request, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(status_code=200, json=payload, request=request)


def test_live_ecos_connector_fetches_base_rate_rows_from_recorded_payload() -> None:
    payload = _load_payload("base_rate_statistic_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == BASE_RATE_PATH
        return _json_response(request, payload)

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    rows = connector.fetch_base_rate_series(START_DATE, END_DATE)

    assert [row.value_date for row in rows] == [START_DATE, date(2024, 1, 3), END_DATE]
    assert [row.base_rate for row in rows] == [Decimal("3.50"), Decimal("3.50"), Decimal("3.50")]
    assert rows[0].metadata.source_name == "ecos"
    assert rows[0].metadata.dataset_name == "base_rate"
    assert rows[0].metadata.api_version == "StatisticSearch"
    assert rows[0].metadata.key_fingerprint_sha256 is not None
    assert len(rows[0].metadata.key_fingerprint_sha256) == 16


def test_live_ecos_connector_raises_on_ecos_auth_failure() -> None:
    payload = {
        "StatisticSearch": {
            "RESULT": {"CODE": "ERROR-301", "MESSAGE": "인증키가 유효하지 않습니다."}
        }
    }

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(lambda request: _json_response(request, payload)),
    )

    with pytest.raises(PermissionError, match="ERROR-301"):
        connector.fetch_base_rate_series(START_DATE, END_DATE)


def test_live_ecos_connector_retries_transient_http_failures() -> None:
    payload = _load_payload("usd_krw_statistic_search.json")
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=503, request=request)
        return _json_response(request, payload)

    slept: list[float] = []
    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
        sleep=slept.append,
    )

    rows = connector.fetch_usd_krw_series(START_DATE, END_DATE)

    assert attempts == 2
    assert slept == [0.5]
    assert [row.exchange_rate for row in rows] == [
        Decimal("1293.10"),
        Decimal("1288.40"),
        Decimal("1290.00"),
    ]


@pytest.mark.parametrize(
    ("fixture_name", "parser", "expected_values"),
    [
        (
            "base_rate_statistic_search.json",
            parse_base_rate_rows,
            (Decimal("3.50"), Decimal("3.50"), Decimal("3.50")),
        ),
        (
            "usd_krw_statistic_search.json",
            parse_usd_krw_rows,
            (Decimal("1293.10"), Decimal("1288.40"), Decimal("1290.00")),
        ),
        (
            "bond_yield_statistic_search.json",
            parse_bond_yield_rows,
            (Decimal("3.23"), Decimal("3.20"), Decimal("3.18")),
        ),
    ],
)
def test_ecos_recorded_payload_parsers_match_expected_values(
    fixture_name: str,
    parser: Callable[[dict[str, object], str, str], tuple[object, ...]],
    expected_values: tuple[Decimal, ...],
) -> None:
    payload = _load_payload(fixture_name)

    rows = parser(
        payload,
        fetched_at_utc="2024-01-15T00:00:00+00:00",
        key_fingerprint_sha256="abc123def4567890",
    )

    assert len(rows) == 3
    assert all(row.metadata.key_fingerprint_sha256 == "abc123def4567890" for row in rows)
    if fixture_name == "base_rate_statistic_search.json":
        assert tuple(row.base_rate for row in rows) == expected_values
    elif fixture_name == "usd_krw_statistic_search.json":
        assert tuple(row.exchange_rate for row in rows) == expected_values
    else:
        assert tuple(row.yield_rate for row in rows) == expected_values
        assert all(row.maturity_code == "3Y" for row in rows)
