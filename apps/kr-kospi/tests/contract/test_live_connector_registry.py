from __future__ import annotations

from collections.abc import Mapping

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.ecos import LiveEcosConnector
from kospi_decision_pipeline_app_kr_kospi.connectors.kosis import LiveKosisConnector
from kospi_decision_pipeline_app_kr_kospi.connectors.krx import PykrxKrxConnector
from kospi_decision_pipeline_app_kr_kospi.connectors.registry import (
    LiveConnectorRegistry,
    resolve_live_api_key,
)


def test_live_connector_registry_returns_pykrx_connector_for_krx() -> None:
    registry = LiveConnectorRegistry()

    assert isinstance(registry.get_connector("krx"), PykrxKrxConnector)


def test_live_connector_registry_returns_live_ecos_connector_with_explicit_api_key() -> None:
    registry = LiveConnectorRegistry(environment={})

    connector = registry.get_connector("ecos", api_key="explicit-ecos-key")

    assert isinstance(connector, LiveEcosConnector)


def test_live_connector_registry_prefers_explicit_key_over_environment() -> None:
    assert (
        resolve_live_api_key(
            source="ecos",
            api_key="explicit-ecos-key",
            environment={"KPUBDATA_BOK_API_KEY": "env-ecos-key"},
        )
        == "explicit-ecos-key"
    )


def test_live_connector_registry_reads_source_specific_environment_key() -> None:
    assert (
        resolve_live_api_key(
            source="ecos",
            api_key=None,
            environment={"KPUBDATA_BOK_API_KEY": "env-ecos-key"},
        )
        == "env-ecos-key"
    )


def test_live_connector_registry_returns_none_for_sources_without_api_keys() -> None:
    assert resolve_live_api_key(source="krx", api_key=None, environment={}) is None


def test_live_connector_registry_rejects_missing_required_api_key() -> None:
    with pytest.raises(ValueError, match="ECOS API key is required"):
        _ = resolve_live_api_key(source="ecos", api_key=None, environment={})


def test_live_connector_registry_returns_live_kosis_connector_with_explicit_api_key() -> None:
    registry = LiveConnectorRegistry(environment={})

    connector = registry.get_connector("kosis", api_key="explicit-kosis-key")

    assert isinstance(connector, LiveKosisConnector)


def test_live_connector_registry_reads_kosis_environment_key() -> None:
    assert (
        resolve_live_api_key(
            source="kosis",
            api_key=None,
            environment={"KPUBDATA_KOSIS_API_KEY": "env-kosis-key"},
        )
        == "env-kosis-key"
    )


def test_live_connector_registry_passes_environment_to_live_kosis_connector() -> None:
    registry = LiveConnectorRegistry(environment={"KPUBDATA_KOSIS_API_KEY": "env-kosis-key"})

    connector = registry.get_connector("kosis")

    environment = getattr(connector, "_environment")
    assert isinstance(environment, Mapping)
    assert environment["KPUBDATA_KOSIS_API_KEY"] == "env-kosis-key"


def test_live_connector_registry_rejects_unknown_source() -> None:
    registry = LiveConnectorRegistry(environment={})

    with pytest.raises(ValueError, match="unsupported source"):
        registry.get_connector("missing")
