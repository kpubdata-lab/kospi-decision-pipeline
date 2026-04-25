from __future__ import annotations

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
