from __future__ import annotations

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
from kospi_decision_pipeline_core.schemas.serialization import parse_decision_result


REPO_ROOT = Path(__file__).resolve().parents[4]
SCENARIO_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "scenario.kospi.next_day.yaml"


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


def _decision_outputs(root: Path) -> dict[str, str]:
    decisions_root = root / "kospi.next_day"
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(decisions_root.glob("*.jsonl"))
    }


def _next_trading_day(current_date: date) -> date:
    calendar = TradingCalendar()
    candidate = current_date + timedelta(days=1)
    while not calendar.is_trading_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError("expected mapping YAML payload")
    return cast(dict[str, object], loaded)


def test_run_cli_executes_gold_fixture_window_deterministically(tmp_path: Path) -> None:
    days = _trading_days(274)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)
    features_path = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
        silver_root=silver_root,
        start=days[-3],
        end=days[-1],
    )
    first_output = tmp_path / "decisions-first"
    second_output = tmp_path / "decisions-second"

    assert (
        main(
            [
                "run",
                "--scenario",
                str(SCENARIO_PATH),
                "--features",
                str(features_path),
                "--out",
                str(first_output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run",
                "--scenario",
                str(SCENARIO_PATH),
                "--features",
                str(features_path),
                "--out",
                str(second_output),
            ]
        )
        == 0
    )

    first_outputs = _decision_outputs(first_output)
    second_outputs = _decision_outputs(second_output)
    expected_decision_dates = [_next_trading_day(day).isoformat() for day in days[-3:]]
    assert first_outputs == second_outputs
    assert tuple(first_outputs) == tuple(
        f"{decision_date}.jsonl" for decision_date in expected_decision_dates
    )

    parsed = [parse_decision_result(content.strip()) for content in first_outputs.values()]
    assert [result.decision_date.isoformat() for result in parsed] == expected_decision_dates
    assert all(result.threshold_up == 0.25 for result in parsed)
    assert all(result.threshold_down == -0.25 for result in parsed)
    assert all(result.snapshot_id.startswith("gold:") for result in parsed)
    assert all(result.label in {"up", "down", "skip"} for result in parsed)
    assert all(len(result.votes) == 5 for result in parsed)
    assert all(
        tuple(vote.agent_name for vote in result.votes)
        == ("domestic_macro", "flow", "technical", "valuation", "volatility")
        for result in parsed
    )


def test_run_cli_uses_agents_yaml_thresholds_for_batch_output(tmp_path: Path) -> None:
    days = _trading_days(274)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)
    features_path = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
        silver_root=silver_root,
        start=days[-1],
        end=days[-1],
    )
    scenario_path = tmp_path / "scenario.yaml"
    agents_path = tmp_path / "agents.yaml"
    output_root = tmp_path / "decisions"
    _write_yaml(
        scenario_path,
        {
            "scenario_id": "kospi.next_day",
            "horizon": "next_day",
            "agents": [
                "technical",
                "domestic_macro",
                "flow",
                "valuation",
                "volatility",
                "decision",
            ],
            "runtime": {
                "agents_config_path": str(agents_path),
                "features_path": str(features_path),
                "output_dir": str(output_root),
            },
        },
    )
    _write_yaml(agents_path, _load_yaml(REPO_ROOT / "apps" / "kr-kospi" / "config" / "agents.yaml"))

    assert (
        main(
            [
                "run",
                "--scenario",
                str(scenario_path),
                "--features",
                str(features_path),
                "--out",
                str(output_root / "default"),
            ]
        )
        == 0
    )

    agents_payload = _load_yaml(agents_path)
    thresholds = cast(dict[str, object], agents_payload["thresholds"])
    thresholds["up"] = 1.0
    _write_yaml(agents_path, agents_payload)

    assert (
        main(
            [
                "run",
                "--scenario",
                str(scenario_path),
                "--features",
                str(features_path),
                "--out",
                str(output_root / "mutated"),
            ]
        )
        == 0
    )

    default_result = parse_decision_result(
        next(iter(_decision_outputs(output_root / "default").values())).strip()
    )
    mutated_result = parse_decision_result(
        next(iter(_decision_outputs(output_root / "mutated").values())).strip()
    )
    assert default_result.label == "up"
    assert mutated_result.label == "skip"
    assert default_result.threshold_up == 0.25
    assert mutated_result.threshold_up == 1.0
