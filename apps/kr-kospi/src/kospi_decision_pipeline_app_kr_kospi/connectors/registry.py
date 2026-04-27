from __future__ import annotations

from typing import final

from . import client_factory
from .ecos import LiveEcosConnector
from .kosis import LiveKosisConnector
from .krx import PykrxKrxConnector


@final
class LiveConnectorRegistry:
    def __init__(self) -> None:
        pass

    def get_connector(self, source: str, *, api_key: str | None = None) -> object:
        del api_key
        if source == "krx":
            return PykrxKrxConnector(client=client_factory.build_client())
        if source == "ecos":
            return LiveEcosConnector(client=client_factory.build_client())
        if source == "kosis":
            return LiveKosisConnector(client=client_factory.build_client())
        raise ValueError(f"unsupported source: {source}")


__all__ = ["LiveConnectorRegistry"]
