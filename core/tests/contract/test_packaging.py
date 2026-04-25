from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "core" / "src"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "kr-kospi" / "src"))


def test_core_and_app_packages_are_importable() -> None:
    package_names = [
        "kospi_decision_pipeline_core",
        "kospi_decision_pipeline_core.schemas",
        "kospi_decision_pipeline_app_kr_kospi",
        "kospi_decision_pipeline_app_kr_kospi.connectors",
        "kospi_decision_pipeline_app_kr_kospi.ingest",
        "kospi_decision_pipeline_app_kr_kospi.transforms",
        "kospi_decision_pipeline_app_kr_kospi.features",
        "kospi_decision_pipeline_app_kr_kospi.agents",
        "kospi_decision_pipeline_app_kr_kospi.scenario",
        "kospi_decision_pipeline_app_kr_kospi.backtest",
        "kospi_decision_pipeline_app_kr_kospi.reporting",
    ]

    for package_name in package_names:
        assert importlib.import_module(package_name) is not None
