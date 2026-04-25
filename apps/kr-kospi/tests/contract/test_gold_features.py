from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import sqrt
from pathlib import Path
from statistics import pstdev
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_app_kr_kospi.transforms.calendar import TradingCalendar
from kospi_decision_pipeline_app_kr_kospi.transforms.gold_features import (
    GoldFeatureBuilder,
    MissingGoldInputError,
    assert_no_forbidden_gold_columns,
    gold_sha256,
)


class _ArrowTable(Protocol):
    @property
    def column_names(self) -> list[str]: ...

    def to_pylist(self) -> list[dict[str, object]]: ...


class _ArrowTableFactory(Protocol):
    def from_pylist(self, mapping: list[dict[str, object]]) -> _ArrowTable: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


class _WriteTable(Protocol):
    def __call__(self, table: _ArrowTable, where: Path, *, compression: str) -> None: ...


def _table_from_pylist(rows: list[dict[str, object]]) -> _ArrowTable:
    factory = cast(_ArrowTableFactory, pa.Table)
    return factory.from_pylist(rows)


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))
WRITE_TABLE = cast(_WriteTable, getattr(pq, "write_table"))


def _read_rows(path: Path) -> list[dict[str, object]]:
    return READ_TABLE(path).to_pylist()


def _write_silver_partition(
    root: Path,
    dataset_id: str,
    partition_date: date,
    row: dict[str, object],
) -> None:
    path = root / dataset_id / f"{partition_date.isoformat()}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist([row]), path, compression="snappy")


def _trading_days(count: int, *, start: date = date(2024, 1, 2)) -> list[date]:
    calendar = TradingCalendar()
    current = start
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


def _build_gold(root: Path, *, days: list[date]) -> Path:
    return GoldFeatureBuilder(output_root=root / "gold").build(
        silver_root=root / "silver",
        start=days[0],
        end=days[-1],
    )


def test_gold_feature_builder_computes_trailing_only_features(tmp_path: Path) -> None:
    days = _trading_days(252)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)

    output_path = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
        silver_root=silver_root,
        start=days[0],
        end=days[-1],
    )

    rows = _read_rows(output_path)
    assert len(rows) == 1
    row = rows[0]

    close_prices = [100 + index for index in range(252)]
    close = close_prices[-1]
    ma5 = sum(close_prices[-5:]) / 5
    ma20 = sum(close_prices[-20:]) / 20
    turnover = [1000 + (10 * index) for index in range(252)]
    foreign = [100 + (2 * index) for index in range(252)]
    institution = [200 + (3 * index) for index in range(252)]
    individual = [-(300 + (5 * index)) for index in range(252)]
    daily_returns = [
        (close_prices[index] / close_prices[index - 1]) - 1 for index in range(1, len(close_prices))
    ]
    realized_vol = pstdev(daily_returns[-20:]) * sqrt(252)

    assert row["as_of_date"] == days[-1]
    assert row["kospi_close"] == pytest.approx(close)
    assert row["kospi_return_1d"] == pytest.approx((close / close_prices[-2]) - 1)
    assert row["kospi_return_3d"] == pytest.approx((close / close_prices[-4]) - 1)
    assert row["kospi_return_5d"] == pytest.approx((close / close_prices[-6]) - 1)
    assert row["kospi_ma5"] == pytest.approx(ma5)
    assert row["kospi_ma20"] == pytest.approx(ma20)
    assert row["kospi_ma5_gap"] == pytest.approx((close - ma5) / ma5)
    assert row["kospi_close_position"] == pytest.approx(1.0)
    assert row["bok_base_rate"] == pytest.approx(5.51)
    assert row["bok_base_rate_change_30d"] == pytest.approx(0.30)
    assert row["usd_krw_close"] == pytest.approx(1451.0)
    assert row["usd_krw_return_5d"] == pytest.approx((1451 / 1446) - 1)
    assert row["kr_bond_yield_3y"] == pytest.approx(4.51)
    assert row["kr_bond_yield_change_30d"] == pytest.approx(0.30)
    assert row["foreign_net_buy_krw_5d_sum"] == pytest.approx(sum(foreign[-5:]))
    assert row["institution_net_buy_krw_5d_sum"] == pytest.approx(sum(institution[-5:]))
    assert row["individual_net_buy_krw_5d_sum"] == pytest.approx(sum(individual[-5:]))
    assert row["foreign_net_buy_5d_pct_of_turnover"] == pytest.approx(
        sum(foreign[-5:]) / sum(turnover[-5:])
    )
    assert row["kospi_per"] == pytest.approx(35.1)
    assert row["kospi_pbr"] == pytest.approx(3.51)
    assert row["kospi_per_percentile_252d"] == pytest.approx(1.0)
    assert row["kospi_pbr_percentile_252d"] == pytest.approx(1.0)
    assert row["kospi_realized_vol_20d"] == pytest.approx(realized_vol)
    assert row["kospi_realized_vol_20d_percentile_252d"] == pytest.approx(1.0)
    assert row["kospi_atr_14d"] == pytest.approx(10.0)
    assert not any(column.startswith("target_") for column in row)
    assert not any(column.startswith("future_") for column in row)


def test_gold_feature_builder_preserves_as_of_date_semantics(tmp_path: Path) -> None:
    days = _trading_days(253)
    first_silver_root = tmp_path / "silver-one"
    second_silver_root = tmp_path / "silver-two"
    _build_complete_silver_history(first_silver_root, days)
    _build_complete_silver_history(second_silver_root, days)

    future_date = days[-1]
    _write_silver_partition(
        second_silver_root,
        "kospi_index",
        future_date,
        {
            "as_of_date": future_date,
            "source_name": "krx",
            "source_series_id": "kospi_index",
            "fetched_at": "2024-01-10T09:00:00+00:00",
            "open": Decimal("1"),
            "high": Decimal("5000"),
            "low": Decimal("1"),
            "close": Decimal("5000"),
            "volume_shares": 999,
            "turnover_krw": Decimal("999999"),
        },
    )

    first_output = GoldFeatureBuilder(output_root=tmp_path / "gold-one").build(
        silver_root=first_silver_root,
        start=days[0],
        end=days[-1],
    )
    second_output = GoldFeatureBuilder(output_root=tmp_path / "gold-two").build(
        silver_root=second_silver_root,
        start=days[0],
        end=days[-1],
    )

    first_rows = _read_rows(first_output)
    second_rows = _read_rows(second_output)
    assert len(first_rows) == 2
    assert len(second_rows) == 2
    assert first_rows[0] == second_rows[0]
    assert first_rows[0]["as_of_date"] == days[-2]


def test_gold_feature_builder_skips_rows_without_full_252d_history(tmp_path: Path) -> None:
    days = _trading_days(251)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)

    output_path = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
        silver_root=silver_root,
        start=days[0],
        end=days[-1],
    )

    assert _read_rows(output_path) == []


def test_gold_feature_builder_raises_typed_error_for_missing_required_input(tmp_path: Path) -> None:
    days = _trading_days(252)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)
    missing_date = days[-1]
    (silver_root / "bond_yield" / f"{missing_date.isoformat()}.parquet").unlink()

    with pytest.raises(MissingGoldInputError, match="bond_yield"):
        _ = GoldFeatureBuilder(output_root=tmp_path / "gold").build(
            silver_root=silver_root,
            start=days[0],
            end=days[-1],
        )


def test_gold_feature_builder_is_deterministic_for_identical_silver_input(tmp_path: Path) -> None:
    days = _trading_days(253)
    silver_root = tmp_path / "silver"
    _build_complete_silver_history(silver_root, days)

    first_path = GoldFeatureBuilder(output_root=tmp_path / "gold-one").build(
        silver_root=silver_root,
        start=days[0],
        end=days[-1],
    )
    second_path = GoldFeatureBuilder(output_root=tmp_path / "gold-two").build(
        silver_root=silver_root,
        start=days[0],
        end=days[-1],
    )

    assert _read_rows(first_path) == _read_rows(second_path)
    assert gold_sha256(first_path) == gold_sha256(second_path)


def test_assert_no_forbidden_gold_columns_rejects_target_and_future_prefixes() -> None:
    with pytest.raises(ValueError, match="target_signal"):
        assert_no_forbidden_gold_columns(["target_signal"])

    with pytest.raises(ValueError, match="future_return_1d"):
        assert_no_forbidden_gold_columns(["future_return_1d"])
