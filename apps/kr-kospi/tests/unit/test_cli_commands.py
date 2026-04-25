from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import runpy

from kospi_decision_pipeline_app_kr_kospi import __version__
from kospi_decision_pipeline_app_kr_kospi.cli import (
    _fixtures_root,
    _parse_date,
    main,
    run_ingest_command,
)


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


def test_cli_main_runs_fixture_ingest(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_ingest_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_ingest_command",
        fake_run_ingest_command,
    )

    assert (
        main(
            [
                "ingest",
                "--source",
                "krx",
                "--dataset",
                "kospi_index",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
                "--out",
                "tmp/bronze",
            ]
        )
        == 0
    )
    assert captured == {
        "source": "krx",
        "dataset": "kospi_index",
        "start": "2024-01-02",
        "end": "2024-01-04",
        "output_dir": "tmp/bronze",
        "live": False,
    }


def test_cli_main_enables_live_mode_with_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_ingest_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_ingest_command",
        fake_run_ingest_command,
    )

    assert (
        main(
            [
                "ingest",
                "--source",
                "krx",
                "--dataset",
                "kospi_index",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
                "--live",
            ]
        )
        == 0
    )
    assert captured["live"] is True


def test_cli_main_enables_live_mode_with_env_var(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_ingest_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_ingest_command",
        fake_run_ingest_command,
    )
    monkeypatch.setenv("KOSPI_LIVE", "1")

    assert (
        main(
            [
                "ingest",
                "--source",
                "krx",
                "--dataset",
                "kospi_index",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
            ]
        )
        == 0
    )
    assert captured["live"] is True


def test_run_ingest_command_writes_fixture_output(tmp_path: Path, capsys) -> None:
    assert (
        run_ingest_command(
            source="krx",
            dataset="kospi_index",
            start="2024-01-02",
            end="2024-01-03",
            output_dir=str(tmp_path),
            live=False,
        )
        == 0
    )

    assert (tmp_path / "krx" / "kospi_index" / "2024-01-02.parquet").is_file()
    assert (tmp_path / "krx" / "kospi_index" / "manifest.json").is_file()
    assert "wrote krx/kospi_index/2024-01-02.parquet sha256=" in capsys.readouterr().out


def test_parse_date_and_fixture_root_helpers() -> None:
    assert _parse_date("2024-01-02").isoformat() == "2024-01-02"
    assert (_fixtures_root() / "krx" / "kospi_index.json").is_file()


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
