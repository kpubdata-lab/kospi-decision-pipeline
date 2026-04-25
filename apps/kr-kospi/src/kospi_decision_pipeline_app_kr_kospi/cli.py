from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path

from .ingest.bronze import BronzeIngestor, FixtureConnectorRegistry, LiveConnectorRegistry
from .transforms.gold_features import GoldFeatureBuilder, gold_lookback_start, gold_sha256
from .transforms.silver import DATASET_DEFINITIONS, SilverNormalizer, silver_sha256


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _is_live_mode_requested(live_flag: bool) -> bool:
    return live_flag or os.getenv("KOSPI_LIVE") == "1"


def run_ingest_command(
    *,
    source: str,
    dataset: str,
    start: str,
    end: str,
    output_dir: str,
    live: bool,
) -> int:
    registry = (
        LiveConnectorRegistry()
        if _is_live_mode_requested(live)
        else FixtureConnectorRegistry(fixtures_root())
    )
    connector = registry.get_connector(source)
    ingestor = BronzeIngestor(output_root=Path(output_dir))
    result = ingestor.ingest(
        connector=connector,
        dataset_id=dataset,
        start=parse_date(start),
        end=parse_date(end),
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
        silver_start = gold_lookback_start(start=start_date, calendar=normalizer._calendar)
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
    live: bool = False


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
    for name in ("run", "backtest", "report"):
        _ = sub.add_parser(name, help=f"{name} (not yet implemented)")
    args = parser.parse_args(argv, namespace=_CliArgs())
    cmd = args.cmd
    if cmd is None:
        parser.print_help()
        return 0
    if cmd == "ingest":
        live_mode = _is_live_mode_requested(bool(args.live))
        return run_ingest_command(
            source=str(args.source),
            dataset=str(args.dataset),
            start=str(args.start),
            end=str(args.end),
            output_dir=str(args.output_dir),
            live=live_mode,
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
    print(f"{cmd}: not yet implemented")
    return 0
