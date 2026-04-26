from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from kospi_decision_pipeline_app_kr_kospi.cli import main
from kospi_decision_pipeline_app_kr_kospi.transforms.calendar import TradingCalendar
from kospi_decision_pipeline_app_kr_kospi.transforms.gold_features import GoldFeatureBuilder


REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIO_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "scenario.kospi.next_day.yaml"
AGENTS_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "agents.yaml"


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


def _write_silver_partition(
    root: Path,
    dataset_id: str,
    partition_date: date,
    row: dict[str, object],
) -> None:
    _write_parquet(root / dataset_id / f"{partition_date.isoformat()}.parquet", [row])


def _write_bronze_close(snapshot_root: Path, trading_date: date, close: Decimal) -> None:
    _write_parquet(
        snapshot_root / "krx" / "kospi_index" / f"{trading_date.isoformat()}.parquet",
        [
            {
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "trade_date": trading_date,
                "open": close - Decimal("1"),
                "high": close + Decimal("5"),
                "low": close - Decimal("5"),
                "close": close,
                "volume_shares": 1_000_000,
                "turnover_krw": Decimal("1000"),
            }
        ],
    )


def _trading_days(count: int) -> list[date]:
    calendar = TradingCalendar()
    current = date(2024, 1, 2)
    days: list[date] = []
    while len(days) < count:
        if calendar.is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def _build_complete_history(silver_root: Path, snapshot_root: Path, days: list[date]) -> None:
    for index, as_of_date in enumerate(days):
        close = Decimal(100 + index)
        _write_bronze_close(snapshot_root, as_of_date, close)
        _write_silver_partition(
            silver_root,
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
            silver_root,
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
            silver_root,
            "base_rate",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "ecos",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "base_rate_pct": Decimal("3.00"),
            },
        )
        _write_silver_partition(
            silver_root,
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
            silver_root,
            "bond_yield",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "ecos",
                "source_series_id": "bond_yield",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "maturity_code": "3Y",
                "yield_rate_pct": Decimal("2.00"),
            },
        )
        _write_silver_partition(
            silver_root,
            "market_valuation",
            as_of_date,
            {
                "as_of_date": as_of_date,
                "source_name": "krx",
                "source_series_id": "market_valuation",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "market_cap_krw": Decimal(2_000_000 + (1000 * index)),
                "trailing_per": Decimal("10.00"),
                "trailing_pbr": Decimal("1.00"),
            },
        )


def test_backtest_cli_is_deterministic_on_fixed_gold_window(tmp_path: Path) -> None:
    days = _trading_days(275)
    silver_root = tmp_path / "silver"
    snapshot_root = tmp_path / "snapshot-root"
    _build_complete_history(silver_root, snapshot_root, days)
    features_path = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
        silver_root=silver_root,
        start=days[-3],
        end=days[-1],
    )
    first_output = tmp_path / "backtest-first"
    second_output = tmp_path / "backtest-second"

    assert (
        main(
            [
                "backtest",
                "--features",
                str(features_path),
                "--snapshot-root",
                str(snapshot_root),
                "--out",
                str(first_output),
                "--scenario",
                str(SCENARIO_PATH),
                "--agents",
                str(AGENTS_PATH),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "backtest",
                "--features",
                str(features_path),
                "--snapshot-root",
                str(snapshot_root),
                "--out",
                str(second_output),
                "--scenario",
                str(SCENARIO_PATH),
                "--agents",
                str(AGENTS_PATH),
            ]
        )
        == 0
    )

    assert (first_output / "rows.jsonl").read_bytes() == (second_output / "rows.jsonl").read_bytes()
    assert (first_output / "summary.json").read_bytes() == (
        second_output / "summary.json"
    ).read_bytes()

    rows_payload = [
        json.loads(line)
        for line in (first_output / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [(row["decision"], row["truth_label"], row["hit"]) for row in rows_payload] == [
        ("up", "up", True),
        ("up", "up", True),
        ("up", "up", True),
    ]
    assert json.loads((first_output / "summary.json").read_text(encoding="utf-8")) == {
        "evaluated_count": 3,
        "hit_count": 3,
        "skip_count": 0,
        "hit_rate": 1.0,
        "skip_rate": 0.0,
        "hit_rate_denominator": "evaluated_count - skip_count (skip excluded)",
    }
