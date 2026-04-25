from __future__ import annotations

import argparse
from typing import cast


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kospi-pipeline")
    _ = parser.add_argument("--version", action="version", version="0.0.1")
    sub = parser.add_subparsers(dest="cmd", required=False)
    for name in ("ingest", "build-features", "run", "backtest", "report"):
        _ = sub.add_parser(name, help=f"{name} (not yet implemented)")
    args = parser.parse_args(argv)
    cmd = cast(str | None, args.cmd)
    if cmd is None:
        parser.print_help()
        return 0
    print(f"{cmd}: not yet implemented")
    return 0
