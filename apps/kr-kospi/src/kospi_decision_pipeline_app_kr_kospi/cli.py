from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date, datetime
import os
from pathlib import Path
from typing import Protocol, cast

import yaml

from kospi_decision_pipeline_core.backtest import BacktestRunner, WalkForwardSplitter
from kospi_decision_pipeline_core.runtime.service import run_kospi_scenario

from .connectors.registry import LiveConnectorRegistry
from .ingest.bronze import BronzeIngestor, FixtureConnectorRegistry
from .transforms.calendar import TradingCalendar
from .transforms.gold_features import GoldFeatureBuilder, gold_lookback_start, gold_sha256
from .transforms.silver import DATASET_DEFINITIONS, SilverNormalizer, silver_sha256


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _is_live_mode_requested(live_flag: bool) -> bool:
    return live_flag or os.getenv("KOSPI_LIVE") == "1"


class ConnectorRegistry(Protocol):
    def get_connector(self, source: str, *, api_key: str | None = None) -> object: ...


def run_ingest_command(
    *,
    source: str,
    dataset: str,
    start: str,
    end: str,
    output_dir: str,
    live: bool,
    snapshot_id: str | None = None,
    api_key: str | None = None,
    connector_registry: ConnectorRegistry | None = None,
    deterministic_run_timestamp: datetime | None = None,
) -> int:
    live_mode = _is_live_mode_requested(live)
    registry = connector_registry or (
        LiveConnectorRegistry()
        if live_mode
        else cast(ConnectorRegistry, FixtureConnectorRegistry(fixtures_root()))
    )
    connector = (
        registry.get_connector(source, api_key=api_key)
        if live_mode
        else cast(FixtureConnectorRegistry, registry).get_connector(source)
    )
    ingestor = BronzeIngestor(
        output_root=Path(output_dir),
        deterministic_run_timestamp=deterministic_run_timestamp,
    )
    result = ingestor.ingest(
        connector=connector,
        source=source,
        dataset_id=dataset,
        start=parse_date(start),
        end=parse_date(end),
        snapshot_id=snapshot_id if live_mode else None,
    )
    for entry in result.entries:
        print(f"wrote {entry.path.as_posix()} sha256={entry.sha256}")
    return 0


def run_build_features_command(
    *,
    layer: str,
    source: str,
    dataset: str,
    start: str,
    end: str,
    bronze_dir: str,
    silver_dir: str,
    output_dir: str,
) -> int:
    start_date = parse_date(start)
    end_date = parse_date(end)
    resolved_output_dir = Path(output_dir)
    if layer == "silver":
        if (source, dataset) not in DATASET_DEFINITIONS:
            raise ValueError(f"unsupported Silver dataset: {source}/{dataset}")
        normalizer = SilverNormalizer(output_root=resolved_output_dir)
        written_paths = normalizer.normalize_dataset(
            bronze_root=Path(bronze_dir),
            source_name=source,
            dataset_id=dataset,
            start=start_date,
            end=end_date,
        )
        for path in written_paths:
            relative_path = path.relative_to(resolved_output_dir)
            print(f"wrote {relative_path.as_posix()} sha256={silver_sha256(path)}")
        return 0
    if layer == "gold":
        output_path = GoldFeatureBuilder(output_root=resolved_output_dir).build(
            silver_root=Path(silver_dir),
            start=start_date,
            end=end_date,
        )
        print(f"wrote {output_path.name} sha256={gold_sha256(output_path)}")
        return 0
    if layer == "all":
        silver_root = Path(silver_dir)
        normalizer = SilverNormalizer(output_root=silver_root)
        silver_start = gold_lookback_start(start=start_date, calendar=TradingCalendar())
        for requirement in GoldFeatureBuilder.REQUIRED_SILVER_DATASETS:
            written_paths = normalizer.normalize_dataset(
                bronze_root=Path(bronze_dir),
                source_name=requirement.source_name,
                dataset_id=requirement.dataset_id,
                start=silver_start,
                end=end_date,
            )
            for path in written_paths:
                relative_path = path.relative_to(silver_root)
                print(f"wrote {relative_path.as_posix()} sha256={silver_sha256(path)}")
        output_path = GoldFeatureBuilder(output_root=resolved_output_dir).build(
            silver_root=silver_root,
            start=start_date,
            end=end_date,
        )
        print(f"wrote {output_path.name} sha256={gold_sha256(output_path)}")
        return 0
    raise ValueError(f"unsupported feature layer: {layer}")


def run_scenario_command(
    *,
    decision_date: str,
    scenario: str,
    features: str,
    output_dir: str,
) -> int:
    _ = run_kospi_scenario(
        Path(scenario),
        parse_date(decision_date),
        Path(features) if features != "" else None,
        Path(output_dir) if output_dir != "" else None,
    )
    return 0


def run_backtest_command(
    *,
    dataset: str,
    scenario: str,
    output_dir: str,
    folds_config: str,
) -> int:
    runner = BacktestRunner(
        splitter=_load_backtest_splitter(folds_config),
        scenario_path=Path(scenario),
        output_dir=Path(output_dir),
    )
    _ = runner.run(dataset_path=Path(dataset))
    return 0


def _load_backtest_splitter(folds_config: str) -> WalkForwardSplitter:
    if folds_config == "":
        return WalkForwardSplitter()
    loaded = cast(object, yaml.safe_load(Path(folds_config).read_text(encoding="utf-8")))
    payload = _ensure_mapping(loaded)
    min_train_rows = _require_int(payload, "min_train_rows")
    test_fold_size = _require_int(payload, "test_fold_size")
    gap_days = _require_int(payload, "gap_days")
    return WalkForwardSplitter(
        min_train_rows=min_train_rows,
        test_fold_size=test_fold_size,
        gap_days=gap_days,
    )


def _require_int(payload: Mapping[str, object], key: str) -> int:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an int")
    return value


def _ensure_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("folds config must be a mapping")
    for key in cast(Mapping[object, object], value):
        if not isinstance(key, str):
            raise ValueError("folds config keys must be strings")
    return cast(Mapping[str, object], value)


class _CliArgs(argparse.Namespace):
    cmd: str | None = None
    layer: str = ""
    source: str = ""
    dataset: str = ""
    start: str = ""
    end: str = ""
    bronze_dir: str = "data/bronze"
    silver_dir: str = "data/silver"
    output_dir: str = ""
    scenario: str = ""
    features: str = ""
    decision_date: str = ""
    folds_config: str = ""
    live: bool = False
    snapshot_id: str = ""
    api_key: str = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kospi-pipeline")
    _ = parser.add_argument("--version", action="version", version="0.0.1")
    sub = parser.add_subparsers(dest="cmd", required=False)
    ingest_parser = sub.add_parser("ingest", help="ingest Bronze data")
    _ = ingest_parser.add_argument(
        "--source", choices=("krx", "ecos", "kosis", "data_portal"), required=True
    )
    _ = ingest_parser.add_argument("--dataset", required=True)
    _ = ingest_parser.add_argument("--from", dest="start", required=True)
    _ = ingest_parser.add_argument("--to", dest="end", required=True)
    _ = ingest_parser.add_argument("--out", dest="output_dir", default="data/bronze")
    _ = ingest_parser.add_argument("--live", action="store_true")
    _ = ingest_parser.add_argument("--snapshot-id", default="")
    _ = ingest_parser.add_argument("--api-key", default="")
    build_features_parser = sub.add_parser("build-features", help="build typed features")
    _ = build_features_parser.add_argument(
        "--layer", choices=("silver", "gold", "all"), required=True
    )
    _ = build_features_parser.add_argument(
        "--source", choices=("krx", "ecos", "kosis", "data_portal"), default=""
    )
    _ = build_features_parser.add_argument("--dataset", default="")
    _ = build_features_parser.add_argument("--from", dest="start", required=True)
    _ = build_features_parser.add_argument("--to", dest="end", required=True)
    _ = build_features_parser.add_argument("--bronze-dir", default="data/bronze")
    _ = build_features_parser.add_argument("--silver-dir", default="data/silver")
    _ = build_features_parser.add_argument("--out", dest="output_dir", default="")
    run_scenario_parser = sub.add_parser("run-scenario", help="run ABDP next-day scenario")
    _ = run_scenario_parser.add_argument("--date", dest="decision_date", required=True)
    _ = run_scenario_parser.add_argument(
        "--scenario",
        default="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
    )
    _ = run_scenario_parser.add_argument("--features", default="")
    _ = run_scenario_parser.add_argument("--out", dest="output_dir", default="")
    run_backtest_parser = sub.add_parser("run-backtest", help="run walk-forward backtest")
    _ = run_backtest_parser.add_argument("--dataset", default="data/gold/backtest_dataset.parquet")
    _ = run_backtest_parser.add_argument(
        "--scenario",
        default="apps/kr-kospi/config/scenario.kospi.next_day.yaml",
    )
    _ = run_backtest_parser.add_argument("--out", dest="output_dir", required=True)
    _ = run_backtest_parser.add_argument("--folds-config", default="")
    for name in ("run", "backtest", "report"):
        _ = sub.add_parser(name, help=f"{name} (not yet implemented)")
    args = parser.parse_args(argv, namespace=_CliArgs())
    cmd = args.cmd
    if cmd is None:
        parser.print_help()
        return 0
    if cmd == "ingest":
        live_mode = _is_live_mode_requested(bool(args.live))
        if live_mode and str(args.snapshot_id).strip() == "":
            parser.error("--snapshot-id is required when live ingest is enabled")
        return run_ingest_command(
            source=str(args.source),
            dataset=str(args.dataset),
            start=str(args.start),
            end=str(args.end),
            output_dir=str(args.output_dir),
            live=live_mode,
            snapshot_id=str(args.snapshot_id) or None,
            api_key=str(args.api_key) or None,
        )
    if cmd == "build-features":
        layer = str(args.layer)
        if layer == "silver" and (str(args.source) == "" or str(args.dataset) == ""):
            build_features_parser.error("--source and --dataset are required when --layer silver")
        output_dir = str(args.output_dir)
        if output_dir == "":
            output_dir = "data/gold" if layer in {"gold", "all"} else "data/silver"
        return run_build_features_command(
            layer=layer,
            source=str(args.source),
            dataset=str(args.dataset),
            start=str(args.start),
            end=str(args.end),
            bronze_dir=str(args.bronze_dir),
            silver_dir=str(args.silver_dir),
            output_dir=output_dir,
        )
    if cmd == "run-scenario":
        return run_scenario_command(
            decision_date=str(args.decision_date),
            scenario=str(args.scenario),
            features=str(args.features),
            output_dir=str(args.output_dir),
        )
    if cmd == "run-backtest":
        return run_backtest_command(
            dataset=str(args.dataset),
            scenario=str(args.scenario),
            output_dir=str(args.output_dir),
            folds_config=str(args.folds_config),
        )
    print(f"{cmd}: not yet implemented")
    return 0
