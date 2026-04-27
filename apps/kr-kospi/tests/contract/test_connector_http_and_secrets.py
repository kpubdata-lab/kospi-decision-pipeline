from __future__ import annotations

import httpx
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors._http import (
    HttpRequestError,
    HttpRetryPolicy,
    SyncHttpRequester,
)
from kospi_decision_pipeline_app_kr_kospi.connectors._secrets import resolve_live_api_key


def test_sync_http_requester_returns_json_response() -> None:
    requester = SyncHttpRequester()

    with httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=200, json={"ok": True}, request=request)
        ),
    ) as client:
        payload = requester.get(client, "/ecos")

    assert payload == {"ok": True}


def test_sync_http_requester_retries_transport_errors_then_succeeds() -> None:
    attempts = 0
    slept: list[float] = []
    requester = SyncHttpRequester(sleep=slept.append)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(status_code=200, json={"ok": True}, request=request)

    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        payload = requester.get(client, "/ecos")

    assert payload == {"ok": True}
    assert attempts == 2
    assert slept == [0.5]


def test_sync_http_requester_raises_after_max_transport_errors() -> None:
    requester = SyncHttpRequester(retry_policy=HttpRetryPolicy(max_attempts=1))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(HttpRequestError, match="1 attempts"):
            requester.get(client, "/ecos")


def test_sync_http_requester_retries_retryable_status_then_raises_after_max_attempts() -> None:
    slept: list[float] = []
    requester = SyncHttpRequester(sleep=slept.append)

    with httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=503, request=request)
        ),
    ) as client:
        with pytest.raises(HttpRequestError, match="3 attempts"):
            requester.get(client, "/ecos")

    assert slept == [0.5, 1.0]


def test_sync_http_requester_raises_immediately_for_non_retryable_status() -> None:
    requester = SyncHttpRequester()

    with httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=404, request=request)
        ),
    ) as client:
        with pytest.raises(HttpRequestError, match="HTTP 404"):
            requester.get(client, "/ecos")


def test_sync_http_requester_raises_without_attempts_when_max_attempts_is_zero() -> None:
    requester = SyncHttpRequester(retry_policy=HttpRetryPolicy(max_attempts=0))

    with httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code=200, json={"ok": True}, request=request)
        ),
    ) as client:
        with pytest.raises(HttpRequestError, match="without response"):
            requester.get(client, "/ecos")


def test_sync_http_requester_exposes_retry_policy_and_backoff_configuration() -> None:
    policy = HttpRetryPolicy(timeout_seconds=9.0, backoff_base_seconds=0.25)
    requester = SyncHttpRequester(retry_policy=policy)

    assert requester.retry_policy is policy
    assert requester.retry_policy.backoff_base_seconds == 0.25


def test_resolve_live_api_key_prefers_explicit_over_environment() -> None:
    assert (
        resolve_live_api_key(
            source="ecos",
            api_key=" explicit-key ",
            environment={"KPUBDATA_BOK_API_KEY": "env-key"},
        )
        == "explicit-key"
    )


def test_resolve_live_api_key_reads_source_specific_environment_key() -> None:
    assert (
        resolve_live_api_key(
            source="kosis",
            api_key=None,
            environment={"KPUBDATA_KOSIS_API_KEY": "env-kosis-key"},
        )
        == "env-kosis-key"
    )


def test_resolve_live_api_key_returns_none_for_sources_without_api_keys() -> None:
    assert resolve_live_api_key(source="krx", api_key=None, environment={}) is None


@pytest.mark.parametrize(
    ("source", "message"),
    [("ecos", "KPUBDATA_BOK_API_KEY"), ("kosis", "KPUBDATA_KOSIS_API_KEY")],
)
def test_resolve_live_api_key_requires_expected_environment_variable(
    source: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_live_api_key(source=source, api_key=None, environment={})
