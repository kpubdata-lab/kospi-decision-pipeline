from __future__ import annotations

import os
from collections.abc import Mapping
from typing import final

from ._secrets import resolve_live_api_key
from .ecos import LiveEcosConnector
from .krx import PykrxKrxConnector


@final
class LiveConnectorRegistry:
    _environment: Mapping[str, str]

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment or os.environ

    def get_connector(self, source: str, *, api_key: str | None = None) -> object:
        if source == "krx":
            return PykrxKrxConnector()
        if source == "ecos":
            return LiveEcosConnector(
                api_key=resolve_live_api_key(
                    source=source,
                    api_key=api_key,
                    environment=self._environment,
                ),
                environment=self._environment,
            )
        if source == "kosis":
            raise NotImplementedError(
                "KOSIS live connector is not implemented yet in v0.2 — see #49"
            )
        raise ValueError(f"unsupported source: {source}")


__all__ = ["LiveConnectorRegistry", "resolve_live_api_key"]
