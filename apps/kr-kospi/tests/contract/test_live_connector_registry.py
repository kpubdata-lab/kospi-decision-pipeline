from __future__ import annotations

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.registry import LiveConnectorRegistry


def test_live_connector_registry_builds_client_for_krx(monkeypatch: pytest.MonkeyPatch) -> None:
    built_client = object()
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.client_factory.build_client",
        lambda: built_client,
    )

    class _FakeKrxConnector:
        def __init__(self, *, client: object) -> None:
            observed["client"] = client

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.PykrxKrxConnector",
        _FakeKrxConnector,
    )

    registry = LiveConnectorRegistry()

    connector = registry.get_connector("krx")

    assert isinstance(connector, _FakeKrxConnector)
    assert observed == {"client": built_client}


def test_live_connector_registry_builds_client_for_ecos(monkeypatch: pytest.MonkeyPatch) -> None:
    built_client = object()
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.client_factory.build_client",
        lambda: built_client,
    )

    class _FakeEcosConnector:
        def __init__(self, *, client: object) -> None:
            observed["client"] = client

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.LiveEcosConnector",
        _FakeEcosConnector,
    )

    registry = LiveConnectorRegistry()

    connector = registry.get_connector("ecos")

    assert isinstance(connector, _FakeEcosConnector)
    assert observed == {"client": built_client}


def test_live_connector_registry_builds_client_for_kosis(monkeypatch: pytest.MonkeyPatch) -> None:
    built_client = object()
    observed: dict[str, object] = {}

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.client_factory.build_client",
        lambda: built_client,
    )

    class _FakeKosisConnector:
        def __init__(self, *, client: object) -> None:
            observed["client"] = client

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.connectors.registry.LiveKosisConnector",
        _FakeKosisConnector,
    )

    registry = LiveConnectorRegistry()

    connector = registry.get_connector("kosis")

    assert isinstance(connector, _FakeKosisConnector)
    assert observed == {"client": built_client}


def test_live_connector_registry_rejects_unknown_source() -> None:
    registry = LiveConnectorRegistry()

    with pytest.raises(ValueError, match="unsupported source"):
        registry.get_connector("missing")
