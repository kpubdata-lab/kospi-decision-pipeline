from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import runpy

import pytest

from kospi_decision_pipeline_app_kr_kospi import __version__
from kospi_decision_pipeline_app_kr_kospi.cli import (
    fixtures_root,
    main,
    parse_date,
    run_build_features_command,
    run_ingest_command,
)
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import (
    BronzeIngestor,
    FixtureConnectorRegistry,
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


def test_cli_main_returns_zero_for_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run"]) == 0
    assert capsys.readouterr().out.strip() == "run: not yet implemented"


def test_cli_main_runs_fixture_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_cli_main_enables_live_mode_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_cli_main_enables_live_mode_with_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_run_ingest_command_writes_fixture_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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


def test_cli_main_routes_build_features_silver_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_build_features_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_build_features_command",
        fake_run_build_features_command,
    )

    assert (
        main(
            [
                "build-features",
                "--layer",
                "silver",
                "--source",
                "krx",
                "--dataset",
                "kospi_index",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-03",
                "--bronze-dir",
                "tmp/bronze",
                "--out",
                "tmp/silver",
            ]
        )
        == 0
    )
    assert captured == {
        "layer": "silver",
        "source": "krx",
        "dataset": "kospi_index",
        "start": "2024-01-02",
        "end": "2024-01-03",
        "bronze_dir": "tmp/bronze",
        "silver_dir": "data/silver",
        "output_dir": "tmp/silver",
    }


def test_cli_main_routes_build_features_gold_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_build_features_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_build_features_command",
        fake_run_build_features_command,
    )

    assert (
        main(
            [
                "build-features",
                "--layer",
                "gold",
                "--from",
                "2024-01-02",
                "--to",
                "2024-12-31",
                "--silver-dir",
                "tmp/silver",
                "--out",
                "tmp/gold",
            ]
        )
        == 0
    )
    assert captured == {
        "layer": "gold",
        "source": "",
        "dataset": "",
        "start": "2024-01-02",
        "end": "2024-12-31",
        "bronze_dir": "data/bronze",
        "silver_dir": "tmp/silver",
        "output_dir": "tmp/gold",
    }


def test_run_build_features_command_writes_silver_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bronze_result = BronzeIngestor(output_root=tmp_path / "bronze").ingest(
        connector=FixtureConnectorRegistry(fixtures_root()).get_connector("krx"),
        dataset_id="kospi_index",
        start=parse_date("2024-01-02"),
        end=parse_date("2024-01-03"),
    )

    assert bronze_result.entries
    assert (
        run_build_features_command(
            layer="silver",
            source="krx",
            dataset="kospi_index",
            start="2024-01-02",
            end="2024-01-03",
            bronze_dir=str(tmp_path / "bronze"),
            silver_dir=str(tmp_path / "silver"),
            output_dir=str(tmp_path / "silver"),
        )
        == 0
    )

    assert (tmp_path / "silver" / "kospi_index" / "2024-01-02.parquet").is_file()
    assert "wrote kospi_index/2024-01-02.parquet sha256=" in capsys.readouterr().out


def test_run_build_features_command_rejects_unsupported_dataset() -> None:
    with pytest.raises(ValueError, match="unsupported Silver dataset"):
        _ = run_build_features_command(
            layer="silver",
            source="krx",
            dataset="missing_dataset",
            start="2024-01-02",
            end="2024-01-03",
            bronze_dir="tmp/bronze",
            silver_dir="tmp/silver",
            output_dir="tmp/silver",
        )


def test_parse_date_and_fixture_root_helpers() -> None:
    assert parse_date("2024-01-02").isoformat() == "2024-01-02"
    assert (fixtures_root() / "krx" / "kospi_index.json").is_file()


def test_cli_main_prints_help_without_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "build-features" in capsys.readouterr().out


def test_cli_main_prints_version_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    try:
        _ = main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0

    assert capsys.readouterr().out.strip() == __version__


def test_module_main_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["kospi_decision_pipeline_app_kr_kospi", "run"])

    try:
        _ = runpy.run_module("kospi_decision_pipeline_app_kr_kospi", run_name="__main__")
    except SystemExit as exc:
        assert exc.code == 0


def test_run_build_features_command_writes_gold_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from kospi_decision_pipeline_app_kr_kospi.transforms.gold_features import GoldFeatureBuilder
    from tests.contract.test_gold_features import _build_complete_silver_history, _trading_days

    days = _trading_days(252)
    _build_complete_silver_history(tmp_path / "silver", days)

    assert (
        run_build_features_command(
            layer="gold",
            source="",
            dataset="",
            start=days[0].isoformat(),
            end=days[-1].isoformat(),
            bronze_dir=str(tmp_path / "bronze"),
            silver_dir=str(tmp_path / "silver"),
            output_dir=str(tmp_path / "gold"),
        )
        == 0
    )

    output_path = tmp_path / "gold" / GoldFeatureBuilder.OUTPUT_FILE_NAME
    assert output_path.is_file()
    assert "wrote decision_features.parquet sha256=" in capsys.readouterr().out
