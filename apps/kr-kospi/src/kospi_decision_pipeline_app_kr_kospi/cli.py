from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path

from .ingest.bronze import BronzeIngestor, FixtureConnectorRegistry, LiveConnectorRegistry
from .transforms.silver import SilverNormalizer, silver_sha256


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
    output_dir: str,
) -> int:
    if layer != "silver":
        print(f"build-features --layer {layer}: not yet implemented")
        return 0
    registry = FixtureConnectorRegistry(fixtures_root())
    connector = registry.get_connector(source)
    bronze_result = BronzeIngestor(output_root=Path(bronze_dir)).ingest(
        connector=connector,
        dataset_id=dataset,
        start=parse_date(start),
        end=parse_date(end),
    )
    normalizer = SilverNormalizer(output_root=Path(output_dir))
    written_paths = normalizer.normalize_ingest_result(bronze_result)
    for path in written_paths:
        relative_path = path.relative_to(Path(output_dir))
        print(f"wrote {relative_path.as_posix()} sha256={silver_sha256(path)}")
    return 0


class _CliArgs(argparse.Namespace):
    cmd: str | None = None
    layer: str = ""
    source: str = ""
    dataset: str = ""
    start: str = ""
    end: str = ""
    bronze_dir: str = "data/bronze"
    output_dir: str = "data/bronze"
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
    _ = build_features_parser.add_argument("--layer", choices=("silver",), required=True)
    _ = build_features_parser.add_argument(
        "--source", choices=("krx", "ecos", "kosis", "data_portal"), required=True
    )
    _ = build_features_parser.add_argument("--dataset", required=True)
    _ = build_features_parser.add_argument("--from", dest="start", required=True)
    _ = build_features_parser.add_argument("--to", dest="end", required=True)
    _ = build_features_parser.add_argument("--bronze-dir", default="data/bronze")
    _ = build_features_parser.add_argument("--out", dest="output_dir", default="data/silver")
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
        return run_build_features_command(
            layer=str(args.layer),
            source=str(args.source),
            dataset=str(args.dataset),
            start=str(args.start),
            end=str(args.end),
            bronze_dir=str(args.bronze_dir),
            output_dir=str(args.output_dir),
        )
    print(f"{cmd}: not yet implemented")
    return 0
