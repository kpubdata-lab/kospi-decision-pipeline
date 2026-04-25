from __future__ import annotations

import socket

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_network: mark test as requiring live network access and skip by default in CI",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
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
