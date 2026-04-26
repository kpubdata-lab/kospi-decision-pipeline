from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import runpy
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_app_kr_kospi import __version__
from kospi_decision_pipeline_app_kr_kospi.cli import (
    fixtures_root,
    main,
    parse_date,
    run_backtest_command,
    run_build_features_command,
    run_ingest_command,
    run_scenario_command,
)
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import (
    BronzeIngestor,
    FixtureConnectorRegistry,
)
from kospi_decision_pipeline_app_kr_kospi.transforms.calendar import TradingCalendar


REPO_ROOT = Path(__file__).resolve().parents[4]
ENV = {
    "PYTHONPATH": str(REPO_ROOT / "core" / "src")
    + ":"
    + str(REPO_ROOT / "apps" / "kr-kospi" / "src"),
}


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


def _write_silver_partition(
    root: Path,
    dataset_id: str,
    partition_date: date,
    row: dict[str, object],
) -> None:
    path = root / dataset_id / f"{partition_date.isoformat()}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist([row]), path, compression="snappy")


def _trading_days(count: int) -> list[date]:
    calendar = TradingCalendar()
    current = date(2024, 1, 2)
    days: list[date] = []
    while len(days) < count:
        if calendar.is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _build_complete_silver_history(root: Path, days: list[date]) -> None:
    for index, as_of_date in enumerate(days):
        close = Decimal(100 + index)
        _write_silver_partition(
            root,
            "kospi_index",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "open": close - Decimal("1"),
                "high": close + Decimal("5"),
                "low": close - Decimal("5"),
                "close": close,
                "volume_shares": 1_000_000 + index,
                "turnover_krw": Decimal(1000 + (10 * index)),
            },
        )
        _write_silver_partition(
            root,
            "investor_flow",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "krx",
                "source_series_id": "investor_flow",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "foreign_net_buy_krw": Decimal(100 + (2 * index)),
                "institution_net_buy_krw": Decimal(200 + (3 * index)),
                "individual_net_buy_krw": Decimal(-(300 + (5 * index))),
            },
        )
        _write_silver_partition(
            root,
            "base_rate",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "ecos",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "base_rate_pct": Decimal("3.00") + (Decimal(index) / Decimal("100")),
            },
        )
        _write_silver_partition(
            root,
            "usd_krw",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "ecos",
                "source_series_id": "usd_krw",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "usd_krw_rate": Decimal(1200 + index),
            },
        )
        _write_silver_partition(
            root,
            "bond_yield",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "ecos",
                "source_series_id": "bond_yield",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "maturity_code": "3Y",
                "yield_rate_pct": Decimal("2.00") + (Decimal(index) / Decimal("100")),
            },
        )
        _write_silver_partition(
            root,
            "market_valuation",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "krx",
                "source_series_id": "market_valuation",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "market_cap_krw": Decimal(2_000_000 + (1000 * index)),
                "trailing_per": Decimal("10.00") + (Decimal(index) / Decimal("10")),
                "trailing_pbr": Decimal("1.00") + (Decimal(index) / Decimal("100")),
            },
        )


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
        "snapshot_id": None,
        "api_key": None,
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
                "--snapshot-id",
                "snapshot-20240115T000000Z",
            ]
        )
        == 0
    )
    assert captured["live"] is True
    assert captured["snapshot_id"] == "snapshot-20240115T000000Z"


def test_cli_main_routes_live_snapshot_id_and_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
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
                "--live",
                "--source",
                "ecos",
                "--dataset",
                "base_rate",
                "--from",
                "2024-01-02",
                "--to",
                "2024-01-04",
                "--snapshot-id",
                "snapshot-20240115T000000Z",
                "--api-key",
                "cli-key",
            ]
        )
        == 0
    )
    assert captured["live"] is True
    assert captured["snapshot_id"] == "snapshot-20240115T000000Z"
    assert captured["api_key"] == "cli-key"


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
                "--snapshot-id",
                "snapshot-20240115T000000Z",
            ]
        )
        == 0
    )
    assert captured["live"] is True
    assert captured["snapshot_id"] == "snapshot-20240115T000000Z"


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


def test_cli_main_requires_source_and_dataset_for_silver(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        _ = main(
            ["build-features", "--layer", "silver", "--from", "2024-01-02", "--to", "2024-01-03"]
        )

    assert "--source and --dataset are required when --layer silver" in capsys.readouterr().err


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


def test_cli_main_routes_run_scenario_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_scenario_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_scenario_command",
        fake_run_scenario_command,
    )

    assert (
        main(
            [
                "run-scenario",
                "--date",
                "2025-02-14",
                "--scenario",
                "apps/kr-kospi/config/scenario.kospi.next_day.yaml",
                "--features",
                "data/gold/features.parquet",
                "--out",
                "data/decisions",
            ]
        )
        == 0
    )
    assert captured == {
        "decision_date": "2025-02-14",
        "scenario": "apps/kr-kospi/config/scenario.kospi.next_day.yaml",
        "features": "data/gold/features.parquet",
        "output_dir": "data/decisions",
    }


def test_cli_main_routes_run_backtest_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_backtest_command(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_backtest_command",
        fake_run_backtest_command,
    )

    assert (
        main(
            [
                "run-backtest",
                "--dataset",
                "data/gold/backtest_dataset.parquet",
                "--scenario",
                "apps/kr-kospi/config/scenario.kospi.next_day.yaml",
                "--out",
                "data/backtest/run-1",
                "--folds-config",
                "config/folds.yaml",
            ]
        )
        == 0
    )
    assert captured == {
        "dataset": "data/gold/backtest_dataset.parquet",
        "scenario": "apps/kr-kospi/config/scenario.kospi.next_day.yaml",
        "output_dir": "data/backtest/run-1",
        "folds_config": "config/folds.yaml",
    }


def test_run_build_features_command_writes_silver_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bronze_result = BronzeIngestor(output_root=tmp_path / "bronze").ingest(
        connector=FixtureConnectorRegistry(fixtures_root()).get_connector("krx"),
        source="krx",
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


def test_run_build_features_command_rejects_unsupported_layer() -> None:
    with pytest.raises(ValueError, match="unsupported feature layer"):
        _ = run_build_features_command(
            layer="unsupported",
            source="",
            dataset="",
            start="2024-01-02",
            end="2024-01-03",
            bronze_dir="tmp/bronze",
            silver_dir="tmp/silver",
            output_dir="tmp/output",
        )


def test_run_scenario_command_returns_zero_after_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_kospi_scenario(
        scenario_path: Path,
        decision_date: date,
        features_path: Path | None,
        output_dir: Path | None,
    ) -> object:
        captured.update(
            {
                "scenario_path": scenario_path,
                "decision_date": decision_date,
                "features_path": features_path,
                "output_dir": output_dir,
            }
        )
        return object()

    monkeypatch.setattr(
        "kospi_decision_pipeline_app_kr_kospi.cli.run_kospi_scenario",
        fake_run_kospi_scenario,
    )

    assert (
        run_scenario_command(
            decision_date="2025-02-14",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            features="data/gold/features.parquet",
            output_dir="data/decisions",
        )
        == 0
    )
    assert captured == {
        "scenario_path": Path("apps/kr-kospi/config/scenario.kospi.next_day.yaml"),
        "decision_date": date(2025, 2, 14),
        "features_path": Path("data/gold/features.parquet"),
        "output_dir": Path("data/decisions"),
    }


def test_run_backtest_command_returns_zero_after_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *, splitter: object, scenario_path: Path, output_dir: Path) -> None:
            captured.update(
                {
                    "splitter": splitter,
                    "scenario_path": scenario_path,
                    "output_dir": output_dir,
                }
            )

        def run(self, *, dataset_path: Path) -> object:
            captured["dataset_path"] = dataset_path
            return object()

    monkeypatch.setattr("kospi_decision_pipeline_app_kr_kospi.cli.BacktestRunner", FakeRunner)

    assert (
        run_backtest_command(
            dataset="data/gold/backtest_dataset.parquet",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            output_dir="data/backtest/run-1",
            folds_config="",
        )
        == 0
    )
    assert captured["scenario_path"] == Path("apps/kr-kospi/config/scenario.kospi.next_day.yaml")
    assert captured["output_dir"] == Path("data/backtest/run-1")
    assert captured["dataset_path"] == Path("data/gold/backtest_dataset.parquet")


def test_run_backtest_command_validates_folds_config(tmp_path: Path) -> None:
    invalid_path = tmp_path / "folds.yaml"
    _ = invalid_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="folds config must be a mapping"):
        _ = run_backtest_command(
            dataset="data/gold/backtest_dataset.parquet",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            output_dir="data/backtest/run-1",
            folds_config=str(invalid_path),
        )

    _ = invalid_path.write_text(
        "min_train_rows: true\ntest_fold_size: 2\ngap_days: 0\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="min_train_rows must be an int"):
        _ = run_backtest_command(
            dataset="data/gold/backtest_dataset.parquet",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            output_dir="data/backtest/run-1",
            folds_config=str(invalid_path),
        )

    _ = invalid_path.write_text("min_train_rows: 2\ntest_fold_size: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required key: gap_days"):
        _ = run_backtest_command(
            dataset="data/gold/backtest_dataset.parquet",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            output_dir="data/backtest/run-1",
            folds_config=str(invalid_path),
        )

    _ = invalid_path.write_text("1: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="folds config keys must be strings"):
        _ = run_backtest_command(
            dataset="data/gold/backtest_dataset.parquet",
            scenario="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
            output_dir="data/backtest/run-1",
            folds_config=str(invalid_path),
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

    days = _trading_days(272)
    _build_complete_silver_history(tmp_path / "silver", days)

    assert (
        run_build_features_command(
            layer="gold",
            source="",
            dataset="",
            start=days[-1].isoformat(),
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


def test_cli_main_uses_gold_default_output_dir(monkeypatch: pytest.MonkeyPatch) -> None:
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
            ]
        )
        == 0
    )
    assert captured["output_dir"] == "data/gold"


def test_run_build_features_command_writes_all_layers_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from kospi_decision_pipeline_app_kr_kospi.transforms.gold_features import GoldFeatureBuilder
    from kospi_decision_pipeline_app_kr_kospi.transforms.silver import SilverNormalizer

    written_silver_path = tmp_path / "silver" / "kospi_index" / "2024-01-02.parquet"
    written_silver_path.parent.mkdir(parents=True, exist_ok=True)
    written_silver_path.write_bytes(b"silver")
    written_gold_path = tmp_path / "gold" / GoldFeatureBuilder.OUTPUT_FILE_NAME
    written_gold_path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(
        _table_from_pylist([{"as_of_date": date(2024, 1, 3), "kospi_close": 1.0}]),
        written_gold_path,
        compression="snappy",
    )

    def fake_normalize_dataset(_self: SilverNormalizer, **_: object) -> tuple[Path, ...]:
        return (written_silver_path,)

    def fake_build(_self: GoldFeatureBuilder, *, silver_root: Path, start: date, end: date) -> Path:
        assert silver_root == tmp_path / "silver"
        assert start.isoformat() == "2025-02-13"
        assert end.isoformat() == "2025-02-14"
        return written_gold_path

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SilverNormalizer, "normalize_dataset", fake_normalize_dataset)
    monkeypatch.setattr(GoldFeatureBuilder, "build", fake_build)

    try:
        assert (
            run_build_features_command(
                layer="all",
                source="",
                dataset="",
                start="2025-02-13",
                end="2025-02-14",
                bronze_dir=str(tmp_path / "bronze"),
                silver_dir=str(tmp_path / "silver"),
                output_dir=str(tmp_path / "gold"),
            )
            == 0
        )
    finally:
        monkeypatch.undo()

    assert written_silver_path.is_file()
    assert written_gold_path.is_file()
    assert "wrote decision_features.parquet sha256=" in capsys.readouterr().out


def test_run_build_features_command_uses_warmup_start_for_all_layer(tmp_path: Path) -> None:
    from kospi_decision_pipeline_app_kr_kospi.transforms.gold_features import (
        GoldFeatureBuilder,
        gold_lookback_start,
    )
    from kospi_decision_pipeline_app_kr_kospi.transforms.silver import SilverNormalizer

    captured_starts: list[date] = []
    written_gold_path = tmp_path / "gold" / GoldFeatureBuilder.OUTPUT_FILE_NAME
    written_gold_path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(
        _table_from_pylist([{"as_of_date": date(2025, 2, 13), "kospi_close": 1.0}]),
        written_gold_path,
        compression="snappy",
    )

    def fake_normalize_dataset(_self: SilverNormalizer, **kwargs: object) -> tuple[Path, ...]:
        start = kwargs.get("start")
        assert isinstance(start, date)
        captured_starts.append(start)
        return ()

    def fake_build(_self: GoldFeatureBuilder, *, silver_root: Path, start: date, end: date) -> Path:
        assert silver_root == tmp_path / "silver"
        assert start == date(2025, 2, 13)
        assert end == date(2025, 2, 13)
        return written_gold_path

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SilverNormalizer, "normalize_dataset", fake_normalize_dataset)
    monkeypatch.setattr(GoldFeatureBuilder, "build", fake_build)

    try:
        assert (
            run_build_features_command(
                layer="all",
                source="",
                dataset="",
                start="2025-02-13",
                end="2025-02-13",
                bronze_dir=str(tmp_path / "bronze"),
                silver_dir=str(tmp_path / "silver"),
                output_dir=str(tmp_path / "gold"),
            )
            == 0
        )
    finally:
        monkeypatch.undo()

    expected_start = gold_lookback_start(start=date(2025, 2, 13), calendar=TradingCalendar())
    assert captured_starts == [expected_start] * len(GoldFeatureBuilder.REQUIRED_SILVER_DATASETS)
