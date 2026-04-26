from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import os

import httpx
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors._http import HttpRequestError
from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import (
    LiveKosisConnector,
    _default_sleep,
    _format_period,
    _utc_now,
    parse_macro_indicator_rows,
)


START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 2, 29)
FETCHED_AT = datetime(2024, 3, 1, tzinfo=timezone.utc)


def _json_response(request: httpx.Request, payload: object) -> httpx.Response:
    return httpx.Response(status_code=200, json=payload, request=request)


def test_parse_macro_indicator_rows_parses_verified_monthly_kosis_payload() -> None:
    rows = parse_macro_indicator_rows(
        payload=[
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
        ],
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


def test_live_kosis_connector_uses_explicit_api_key_over_environment() -> None:
    expected_fingerprint = hashlib.sha256("explicit-kosis-key".encode("utf-8")).hexdigest()[:16]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["apiKey"] == "explicit-kosis-key"
        assert request.url.params["orgId"] == "101"
        assert request.url.params["tblId"] == "DT_1J22003"
        assert request.url.params["itmId"] == "T"
        assert request.url.params["objL1"] == "T10"
        assert request.url.params["prdSe"] == "M"
        assert request.url.params["startPrdDe"] == "202401"
        assert request.url.params["endPrdDe"] == "202402"
        return _json_response(
            request,
            [
                {
                    "PRD_DE": "202401",
                    "DT": "100.1",
                    "C1_OBJ_NM": "반도체",
                    "UNIT_NM": "2020=100",
                }
            ],
        )

    connector = LiveKosisConnector(
        api_key="explicit-kosis-key",
        environment={"KOSIS_API_KEY": "env-kosis-key"},
        transport=httpx.MockTransport(handler),
        now=lambda: FETCHED_AT,
    )

    rows = connector.fetch_macro_indicators(START_DATE, END_DATE)

    assert rows[0].metadata.key_fingerprint_sha256 == expected_fingerprint


def test_live_kosis_connector_requires_api_key_when_no_auth_source_exists() -> None:
    with pytest.raises(ValueError, match="KOSIS API key is required"):
        LiveKosisConnector(environment={})


@pytest.mark.parametrize("status_code", [401, 403])
def test_live_kosis_connector_maps_http_auth_failure_to_permission_error(status_code: int) -> None:
    connector = LiveKosisConnector(
        api_key="test-kosis-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=status_code, request=request)
        ),
    )

    with pytest.raises(PermissionError, match=f"HTTP {status_code}"):
        connector.fetch_macro_indicators(START_DATE, END_DATE)


def test_live_kosis_connector_rejects_unsupported_live_dataset_shape() -> None:
    connector = LiveKosisConnector(api_key="test-kosis-key")

    with pytest.raises(ValueError, match="per_pbr_percentiles"):
        connector.fetch_per_pbr_percentiles(START_DATE, END_DATE)


def test_live_kosis_connector_reraises_non_auth_http_failures() -> None:
    connector = LiveKosisConnector(
        api_key="test-kosis-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=500, request=request)
        ),
        sleep=lambda _seconds: None,
    )

    with pytest.raises(HttpRequestError, match="HTTP request failed after 3 attempts"):
        connector.fetch_macro_indicators(START_DATE, END_DATE)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "JSON array"),
        (["bad-row"], "JSON object"),
        ([{"DT": "1.0"}], "PRD_DE"),
        ([{"PRD_DE": 202401, "DT": "1.0"}], "PRD_DE"),
        ([{"PRD_DE": "202401", "DT": 1.0}], "DT"),
        ([{"PRD_DE": "202401", "DT": "1.0", "C1_OBJ_NM": 1}], "C1_OBJ_NM"),
        ([{"PRD_DE": "202401", "DT": "1.0", "UNIT_NM": 1}], "UNIT_NM"),
        ([{"PRD_DE": "2024", "DT": "1.0"}], "unsupported KOSIS period format"),
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
        payload=[{"PRD_DE": "202401", "DT": "99.9"}],
        dataset_name="macro_indicators",
        fetched_at_utc=FETCHED_AT.isoformat(),
        key_fingerprint_sha256="fingerprint123456",
        series_name="verified-series",
        unit="index",
    )

    assert rows[0].indicator_name == "verified-series"
    assert rows[0].unit == "index"


def test_kosis_period_helpers_cover_supported_and_unsupported_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _format_period(date(2024, 2, 29), "M") == "202402"

    with pytest.raises(ValueError, match="unsupported KOSIS period type"):
        _format_period(date(2024, 2, 29), "D")

    slept: list[float] = []
    monkeypatch.setattr("time.sleep", slept.append)
    _default_sleep(0.25)

    assert slept == [0.25]
    assert _utc_now().tzinfo == timezone.utc


@pytest.mark.skipif(os.getenv("KOSIS_API_KEY") is None, reason="KOSIS_API_KEY not set")
def test_live_kosis_connector_smoke_fetches_verified_bronze_series() -> None:
    connector = LiveKosisConnector(now=lambda: FETCHED_AT)

    rows = connector.fetch_macro_indicators(date(2024, 1, 1), date(2024, 3, 31))

    assert rows
    assert rows[0].metadata.source_name == "kosis"
    assert rows[0].metadata.dataset_name == "macro_indicators"
    assert rows[0].indicator_name != ""
