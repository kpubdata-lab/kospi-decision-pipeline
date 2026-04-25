from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path

from .ingest.bronze import BronzeIngestor, FixtureConnectorRegistry, LiveConnectorRegistry


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _fixtures_root() -> Path:
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
        else FixtureConnectorRegistry(_fixtures_root())
    )
    connector = registry.get_connector(source)
    ingestor = BronzeIngestor(output_root=Path(output_dir))
    result = ingestor.ingest(
        connector=connector,
        dataset_id=dataset,
        start=_parse_date(start),
        end=_parse_date(end),
    )
    for entry in result.entries:
        print(f"wrote {entry.path.as_posix()} sha256={entry.sha256}")
    return 0


class _CliArgs(argparse.Namespace):
    cmd: str | None = None
    source: str = ""
    dataset: str = ""
    start: str = ""
    end: str = ""
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
    for name in ("build-features", "run", "backtest", "report"):
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
    print(f"{cmd}: not yet implemented")
    return 0
