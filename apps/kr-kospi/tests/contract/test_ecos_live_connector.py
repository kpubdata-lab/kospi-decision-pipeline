from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import cast

import httpx
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors._http import (
    HttpRequestError,
    HttpRetryPolicy,
    SyncHttpRequester,
)
from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import (
    LiveEcosConnector,
    EcosBaseRateRow,
    EcosBondYieldRow,
    EcosUsdKrwRow,
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
BOND_YIELD_PATH = (
    "/api/StatisticSearch/test-api-key/json/kr/1/100000/817Y002/D/20240102/20240104/010200000"
)


def _load_payload(name: str) -> Mapping[str, object]:
    return cast(
        Mapping[str, object], json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8"))
    )


EcosRow = EcosBaseRateRow | EcosUsdKrwRow | EcosBondYieldRow


def _load_payload_dict(name: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((FIXTURES_ROOT / name).read_text(encoding="utf-8")))


def _json_response(request: httpx.Request, payload: Mapping[str, object]) -> httpx.Response:
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


def test_live_ecos_connector_prefers_explicit_api_key_over_environment() -> None:
    payload = _load_payload("base_rate_statistic_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "explicit-api-key" in request.url.path
        assert "env-api-key" not in request.url.path
        return _json_response(request, payload)

    connector = LiveEcosConnector(
        api_key="explicit-api-key",
        environment={"KPUBDATA_BOK_API_KEY": "env-api-key"},
        transport=httpx.MockTransport(handler),
    )

    rows = connector.fetch_base_rate_series(START_DATE, END_DATE)

    assert rows


def test_live_ecos_connector_requires_api_key_when_no_auth_source_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KPUBDATA_BOK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ECOS API key"):
        LiveEcosConnector(environment={})


def test_live_ecos_connector_uses_environment_api_key() -> None:
    payload = _load_payload("usd_krw_statistic_search.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "env-api-key" in request.url.path
        return _json_response(request, payload)

    connector = LiveEcosConnector(
        environment={"KPUBDATA_BOK_API_KEY": "env-api-key"},
        transport=httpx.MockTransport(handler),
    )

    rows = connector.fetch_usd_krw_series(START_DATE, END_DATE)

    assert rows


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


def test_live_ecos_connector_uses_default_sleep_for_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _load_payload("usd_krw_statistic_search.json")
    attempts = 0
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=503, request=request)
        return _json_response(request, payload)

    monkeypatch.setattr("time.sleep", slept.append)

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    rows = connector.fetch_usd_krw_series(START_DATE, END_DATE)

    assert attempts == 2
    assert slept == [0.5]
    assert rows


def test_live_ecos_connector_fetches_bond_yield_rows() -> None:
    payload = _load_payload("bond_yield_statistic_search.json")

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(lambda request: _json_response(request, payload)),
    )

    rows = connector.fetch_bond_yield_series(START_DATE, END_DATE)

    assert tuple(row.yield_rate for row in rows) == (
        Decimal("3.23"),
        Decimal("3.20"),
        Decimal("3.18"),
    )
    assert all(row.maturity_code == "3Y" for row in rows)


@pytest.mark.parametrize(
    (
        "fixture_name",
        "request_path",
        "fetcher_name",
        "dataset_name",
        "value_attr",
        "expected_values",
    ),
    [
        (
            "base_rate_statistic_search.json",
            BASE_RATE_PATH,
            "fetch_base_rate_series",
            "base_rate",
            "base_rate",
            (Decimal("3.50"), Decimal("3.50"), Decimal("3.50")),
        ),
        (
            "usd_krw_statistic_search.json",
            USD_KRW_PATH,
            "fetch_usd_krw_series",
            "usd_krw",
            "exchange_rate",
            (Decimal("1293.10"), Decimal("1288.40"), Decimal("1290.00")),
        ),
        (
            "bond_yield_statistic_search.json",
            BOND_YIELD_PATH,
            "fetch_bond_yield_series",
            "bond_yield",
            "yield_rate",
            (Decimal("3.23"), Decimal("3.20"), Decimal("3.18")),
        ),
    ],
)
def test_live_ecos_connector_replays_recorded_success_payloads_for_all_series(
    fixture_name: str,
    request_path: str,
    fetcher_name: str,
    dataset_name: str,
    value_attr: str,
    expected_values: tuple[Decimal, ...],
) -> None:
    payload = _load_payload(fixture_name)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == request_path
        return _json_response(request, payload)

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    rows = cast(tuple[EcosRow, ...], getattr(connector, fetcher_name)(START_DATE, END_DATE))

    assert tuple(getattr(row, value_attr) for row in rows) == expected_values
    assert tuple(row.value_date for row in rows) == (START_DATE, date(2024, 1, 3), END_DATE)
    assert rows[0].metadata.dataset_name == dataset_name


@pytest.mark.parametrize(
    ("fixture_name", "fetcher_name"),
    [
        ("base_rate_auth_error_statistic_search.json", "fetch_base_rate_series"),
        ("usd_krw_auth_error_statistic_search.json", "fetch_usd_krw_series"),
        ("bond_yield_auth_error_statistic_search.json", "fetch_bond_yield_series"),
    ],
)
def test_live_ecos_connector_raises_on_recorded_auth_failures_for_all_series(
    fixture_name: str,
    fetcher_name: str,
) -> None:
    payload = _load_payload(fixture_name)
    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(lambda request: _json_response(request, payload)),
    )

    with pytest.raises(PermissionError, match="ERROR-301"):
        _ = getattr(connector, fetcher_name)(START_DATE, END_DATE)


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
    parser: Callable[[object, str, str], tuple[EcosRow, ...]],
    value_attr: str,
    expected_values: tuple[Decimal, ...],
) -> None:
    payload = _load_payload_dict(fixture_name)
    statistic_search = cast(dict[str, object], payload["StatisticSearch"])
    rows = cast(list[object], statistic_search["row"])
    statistic_search["row"] = list(reversed(rows))

    parsed_rows = parser(payload, "2024-01-15T00:00:00+00:00", "abc123def4567890")

    assert tuple(row.value_date for row in parsed_rows) == (START_DATE, date(2024, 1, 3), END_DATE)
    assert tuple(getattr(row, value_attr) for row in parsed_rows) == expected_values


@pytest.mark.parametrize(
    ("fixture_name", "parser"),
    [
        ("base_rate_empty_window_statistic_search.json", parse_base_rate_rows),
        ("usd_krw_empty_window_statistic_search.json", parse_usd_krw_rows),
        ("bond_yield_empty_window_statistic_search.json", parse_bond_yield_rows),
    ],
)
def test_parse_ecos_rows_return_empty_tuple_for_recorded_empty_windows(
    fixture_name: str,
    parser: Callable[[object, str, str], tuple[object, ...]],
) -> None:
    rows = parser(
        _load_payload(fixture_name),
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert rows == ()


@pytest.mark.parametrize(
    ("fixture_name", "fetcher_name", "value_attr", "expected_values"),
    [
        (
            "base_rate_statistic_search.json",
            "fetch_base_rate_series",
            "base_rate",
            (Decimal("3.50"), Decimal("3.50"), Decimal("3.50")),
        ),
        (
            "usd_krw_statistic_search.json",
            "fetch_usd_krw_series",
            "exchange_rate",
            (Decimal("1293.10"), Decimal("1288.40"), Decimal("1290.00")),
        ),
        (
            "bond_yield_statistic_search.json",
            "fetch_bond_yield_series",
            "yield_rate",
            (Decimal("3.23"), Decimal("3.20"), Decimal("3.18")),
        ),
    ],
)
def test_live_ecos_connector_retries_5xx_for_all_series(
    fixture_name: str,
    fetcher_name: str,
    value_attr: str,
    expected_values: tuple[Decimal, ...],
) -> None:
    payload = _load_payload(fixture_name)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=503, request=request)
        return _json_response(request, payload)

    connector = LiveEcosConnector(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )

    rows = cast(tuple[object, ...], getattr(connector, fetcher_name)(START_DATE, END_DATE))

    assert attempts == 2
    assert tuple(getattr(row, value_attr) for row in rows) == expected_values


def test_parse_base_rate_rows_returns_empty_tuple_when_row_block_missing() -> None:
    rows = parse_base_rate_rows(
        {"StatisticSearch": {"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."}}},
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert rows == ()


def test_parse_base_rate_rows_raises_runtime_error_for_non_auth_ecos_failure() -> None:
    payload = {"StatisticSearch": {"RESULT": {"CODE": "ERROR-100", "MESSAGE": "잘못된 요청"}}}

    with pytest.raises(RuntimeError, match="ERROR-100"):
        parse_base_rate_rows(payload, "2024-01-15T00:00:00+00:00", "abc123def4567890")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-a-dict", "JSON object"),
        ({"StatisticSearch": []}, "StatisticSearch"),
        ({"StatisticSearch": {"RESULT": []}}, "RESULT"),
        (
            {"StatisticSearch": {"RESULT": {"CODE": 123, "MESSAGE": "정상 처리되었습니다."}}},
            "CODE",
        ),
        (
            {
                "StatisticSearch": {
                    "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."},
                    "row": {},
                }
            },
            "row payload must be a list",
        ),
        (
            {
                "StatisticSearch": {
                    "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."},
                    "row": ["not-a-dict"],
                }
            },
            "JSON object",
        ),
        (
            {
                "StatisticSearch": {
                    "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다."},
                    "row": [{"TIME": "20240102", "DATA_VALUE": 1.23}],
                }
            },
            "DATA_VALUE",
        ),
    ],
)
def test_parse_base_rate_rows_validates_ecos_payload_shape(payload: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_base_rate_rows(payload, "2024-01-15T00:00:00+00:00", "abc123def4567890")


def test_sync_http_requester_retries_transport_errors() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return _json_response(request, _load_payload("base_rate_statistic_search.json"))

    requester = SyncHttpRequester(sleep=sleeps.append)
    with httpx.Client(
        base_url="https://example.com", transport=httpx.MockTransport(handler)
    ) as client:
        payload = requester.get(client, "/payload")

    assert attempts == 2
    assert sleeps == [0.5]
    assert isinstance(payload, Mapping)


def test_sync_http_requester_raises_for_non_retryable_http_status() -> None:
    requester = SyncHttpRequester()
    with httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(404, request=request)),
    ) as client:
        with pytest.raises(HttpRequestError, match="HTTP 404"):
            requester.get(client, "/missing")


def test_sync_http_requester_raises_after_retry_exhaustion() -> None:
    requester = SyncHttpRequester(sleep=lambda _seconds: None)
    with httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, request=request)),
    ) as client:
        with pytest.raises(HttpRequestError, match="3 attempts"):
            requester.get(client, "/retry")


def test_sync_http_requester_raises_after_last_transport_error() -> None:
    requester = SyncHttpRequester(HttpRetryPolicy(max_attempts=1), sleep=lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(HttpRequestError, match="1 attempts"):
            requester.get(client, "/timeout")


def test_sync_http_requester_rejects_zero_attempt_policy() -> None:
    requester = SyncHttpRequester(HttpRetryPolicy(max_attempts=0))
    with httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(lambda request: _json_response(request, {})),
    ) as client:
        with pytest.raises(HttpRequestError, match="without response"):
            requester.get(client, "/never-called")


def test_parse_base_rate_rows_matches_recorded_payload() -> None:
    rows = parse_base_rate_rows(
        _load_payload("base_rate_statistic_search.json"),
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert len(rows) == 3
    assert tuple(row.base_rate for row in rows) == (
        Decimal("3.50"),
        Decimal("3.50"),
        Decimal("3.50"),
    )
    assert all(row.metadata.key_fingerprint_sha256 == "abc123def4567890" for row in rows)


def test_parse_usd_krw_rows_matches_recorded_payload() -> None:
    rows = parse_usd_krw_rows(
        _load_payload("usd_krw_statistic_search.json"),
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert len(rows) == 3
    assert tuple(row.exchange_rate for row in rows) == (
        Decimal("1293.10"),
        Decimal("1288.40"),
        Decimal("1290.00"),
    )
    assert all(row.metadata.key_fingerprint_sha256 == "abc123def4567890" for row in rows)


def test_parse_bond_yield_rows_matches_recorded_payload() -> None:
    rows = parse_bond_yield_rows(
        _load_payload("bond_yield_statistic_search.json"),
        "2024-01-15T00:00:00+00:00",
        "abc123def4567890",
    )

    assert len(rows) == 3
    assert tuple(row.yield_rate for row in rows) == (
        Decimal("3.23"),
        Decimal("3.20"),
        Decimal("3.18"),
    )
    assert all(row.maturity_code == "3Y" for row in rows)
    assert all(row.metadata.key_fingerprint_sha256 == "abc123def4567890" for row in rows)
