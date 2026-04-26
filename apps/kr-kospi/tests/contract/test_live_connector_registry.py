from __future__ import annotations

import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.krx import PykrxKrxConnector
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import LiveConnectorRegistry


def test_live_connector_registry_returns_pykrx_connector_for_krx() -> None:
    registry = LiveConnectorRegistry()

    assert isinstance(registry.get_connector("krx"), PykrxKrxConnector)


def test_live_connector_registry_rejects_non_krx_sources() -> None:
    registry = LiveConnectorRegistry()

    with pytest.raises(NotImplementedError, match="live connector not implemented"):
        registry.get_connector("ecos")
