from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import runpy

from kospi_decision_pipeline_app_kr_kospi import __version__
from kospi_decision_pipeline_app_kr_kospi.cli import main


REPO_ROOT = Path(__file__).resolve().parents[4]
ENV = {
    "PYTHONPATH": str(REPO_ROOT / "core" / "src")
    + ":"
    + str(REPO_ROOT / "apps" / "kr-kospi" / "src"),
}


def test_cli_stub_subcommand_output() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "kospi_decision_pipeline_app_kr_kospi", "run"],
        cwd=REPO_ROOT,
        env=ENV,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "run: not yet implemented"


def test_cli_main_returns_zero_for_run(capsys) -> None:
    assert main(["run"]) == 0
    assert capsys.readouterr().out.strip() == "run: not yet implemented"


def test_cli_main_prints_help_without_command(capsys) -> None:
    assert main([]) == 0
    assert "build-features" in capsys.readouterr().out


def test_cli_main_prints_version_and_exits(capsys) -> None:
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    assert capsys.readouterr().out.strip() == __version__


def test_module_main_raises_system_exit(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kospi_decision_pipeline_app_kr_kospi", "run"])

    try:
        runpy.run_module("kospi_decision_pipeline_app_kr_kospi", run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0
