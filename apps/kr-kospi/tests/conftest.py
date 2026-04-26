from __future__ import annotations

import socket
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_network: mark test as requiring live network access and skip by default in CI",
    )
    config.addinivalue_line(
        "markers",
        "live: mark live integration tests gated by environment variables",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    live_enabled = {
        "KOSPI_PIPELINE_LIVE_ECOS": os.getenv("KOSPI_PIPELINE_LIVE_ECOS") == "1",
        "KOSPI_PIPELINE_LIVE_KRX": os.getenv("KOSPI_PIPELINE_LIVE_KRX") == "1",
    }
    for item in items:
        if "live" not in item.keywords:
            continue
        module_name = str(item.module.__name__)
        if module_name.endswith("test_ecos_live") and not live_enabled["KOSPI_PIPELINE_LIVE_ECOS"]:
            item.add_marker(
                pytest.mark.skip(reason="set KOSPI_PIPELINE_LIVE_ECOS=1 to run live ECOS tests")
            )
        if module_name.endswith("test_krx_live") and not live_enabled["KOSPI_PIPELINE_LIVE_KRX"]:
            item.add_marker(
                pytest.mark.skip(reason="set KOSPI_PIPELINE_LIVE_KRX=1 to run live KRX tests")
            )
    if not config.getoption("--run-network", default=False):
        skip_network = pytest.mark.skip(reason="requires network; pass --run-network to enable")
        for item in items:
            if "requires_network" in item.keywords:
                item.add_marker(skip_network)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run tests marked with requires_network",
    )


@pytest.fixture(autouse=True)
def block_network_by_default(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    if request.node.get_closest_marker("requires_network") is not None:
        return
    if request.node.get_closest_marker("live") is not None:
        return

    def fail_create_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            f"unexpected network access via create_connection: {args!r} {kwargs!r}"
        )

    def fail_connect(_self: socket.socket, address: object) -> None:
        raise AssertionError(f"unexpected network access via connect: {address!r}")

    def fail_connect_ex(_self: socket.socket, address: object) -> int:
        raise AssertionError(f"unexpected network access via connect_ex: {address!r}")

    monkeypatch.setattr(socket, "create_connection", fail_create_connection)
    monkeypatch.setattr(socket.socket, "connect", fail_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_connect_ex)
