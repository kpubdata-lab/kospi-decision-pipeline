from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
ENV = {
    "PYTHONPATH": str(REPO_ROOT / "core" / "src")
    + ":"
    + str(REPO_ROOT / "apps" / "kr-kospi" / "src"),
}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "kospi_decision_pipeline_app_kr_kospi", *args],
        cwd=REPO_ROOT,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_version() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == "0.0.1"


def test_cli_help_lists_stubbed_subcommands() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    for name in ("ingest", "build-features", "run", "backtest", "report"):
        assert name in result.stdout
