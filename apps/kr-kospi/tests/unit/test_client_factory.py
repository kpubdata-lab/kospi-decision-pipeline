from __future__ import annotations

import click
from kpubdata import Client
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.client_factory import build_client


def _clear_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("KPUBDATA_BOK_API_KEY", "KPUBDATA_KOSIS_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_build_client_raises_when_both_keys_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)

    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    assert "KPUBDATA_BOK_API_KEY" in str(exc_info.value)
    assert "KPUBDATA_KOSIS_API_KEY" in str(exc_info.value)


def test_build_client_raises_when_only_bok_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("KPUBDATA_KOSIS_API_KEY", "test-kosis-key")

    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    assert "KPUBDATA_BOK_API_KEY" in str(exc_info.value)
    assert "KPUBDATA_KOSIS_API_KEY" not in str(exc_info.value)


def test_build_client_raises_when_only_kosis_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "test-bok-key")

    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    assert "KPUBDATA_KOSIS_API_KEY" in str(exc_info.value)
    assert "KPUBDATA_BOK_API_KEY" not in str(exc_info.value)


def test_build_client_ignores_legacy_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ECOS_API_KEY", "legacy-ecos-key")
    monkeypatch.setenv("KOSIS_API_KEY", "legacy-kosis-key")

    with pytest.raises(click.ClickException) as exc_info:
        build_client()

    assert "KPUBDATA_BOK_API_KEY" in str(exc_info.value)
    assert "KPUBDATA_KOSIS_API_KEY" in str(exc_info.value)


def test_build_client_succeeds_when_both_keys_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "test-bok-key")
    monkeypatch.setenv("KPUBDATA_KOSIS_API_KEY", "test-kosis-key")

    client = build_client()

    assert client is not None


def test_returned_client_is_kpubdata_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("KPUBDATA_BOK_API_KEY", "test-bok-key")
    monkeypatch.setenv("KPUBDATA_KOSIS_API_KEY", "test-kosis-key")

    client = build_client()

    assert isinstance(client, Client)


def test_build_client_allows_authless_provider_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_auth_env(monkeypatch)

    client = build_client(required_providers=())

    assert isinstance(client, Client)
