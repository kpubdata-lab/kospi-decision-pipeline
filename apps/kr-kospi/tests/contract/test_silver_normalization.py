from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from kospi_decision_pipeline_app_kr_kospi.connectors.fixture import (
    FixtureEcosConnector,
    FixtureKosisConnector,
    FixtureKrxConnector,
)
from kospi_decision_pipeline_app_kr_kospi.ingest.bronze import BronzeIngestor
from kospi_decision_pipeline_app_kr_kospi.transforms.calendar import TradingCalendar
from kospi_decision_pipeline_app_kr_kospi.transforms.silver import (
    DATASET_DEFINITIONS,
    DatasetDefinition,
    InvalidValueError,
    MissingFieldError,
    NonTradingDayError,
    SilverNormalizer,
    assert_no_forbidden_columns,
    silver_sha256,
)


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
RUN_TIMESTAMP = datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc)


class _ArrowTable(Protocol):
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


def _write_bronze_partition(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    WRITE_TABLE(_table_from_pylist(rows), path, compression="snappy")


@pytest.mark.parametrize(
    ("connector", "dataset_id", "expected_relative_path", "expected_row"),
    [
        (
            FixtureKrxConnector(FIXTURES_ROOT),
            "kospi_index",
            Path("kospi_index/2024-01-02.parquet"),
            {
                "as_of_date": date(2024, 1, 2),
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "open": Decimal("2645.50"),
                "high": Decimal("2660.00"),
                "low": Decimal("2642.20"),
                "close": Decimal("2658.10"),
                "volume_shares": 1020000,
                "turnover_krw": Decimal("852500000000.00"),
            },
        ),
        (
            FixtureKrxConnector(FIXTURES_ROOT),
            "investor_flow",
            Path("investor_flow/2024-01-02.parquet"),
            {
                "as_of_date": date(2024, 1, 2),
                "source_name": "krx",
                "source_series_id": "investor_flow",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "individual_net_buy_krw": Decimal("-400000000"),
                "foreign_net_buy_krw": Decimal("700000000"),
                "institution_net_buy_krw": Decimal("-300000000"),
            },
        ),
        (
            FixtureEcosConnector(FIXTURES_ROOT),
            "base_rate",
            Path("base_rate/2024-01-02.parquet"),
            {
                "as_of_date": date(2024, 1, 2),
                "source_name": "ecos",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "base_rate_pct": Decimal("3.50"),
            },
        ),
        (
            FixtureKosisConnector(FIXTURES_ROOT),
            "per_pbr_percentiles",
            Path("per_pbr_percentiles/2024-01-02.parquet"),
            {
                "as_of_date": date(2024, 1, 2),
                "source_name": "kosis",
                "source_series_id": "per_pbr_percentiles",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "per_percentile_pct": Decimal("42.1"),
                "pbr_percentile_pct": Decimal("39.2"),
            },
        ),
    ],
)
def test_silver_normalizer_normalizes_fixture_bronze_rows(
    tmp_path: Path,
    connector: object,
    dataset_id: str,
    expected_relative_path: Path,
    expected_row: dict[str, object],
) -> None:
    bronze_ingestor = BronzeIngestor(
        output_root=tmp_path / "bronze",
        deterministic_run_timestamp=RUN_TIMESTAMP,
    )
    bronze_result = bronze_ingestor.ingest(
        connector=connector,
        dataset_id=dataset_id,
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )

    silver_normalizer = SilverNormalizer(output_root=tmp_path / "silver")

    written_paths = silver_normalizer.normalize_ingest_result(bronze_result)

    assert written_paths == (tmp_path / "silver" / expected_relative_path,)
    assert _read_rows(written_paths[0]) == [expected_row]
    assert all(not column.startswith("target_") for column in _read_rows(written_paths[0])[0])


def test_silver_normalizer_raises_typed_error_for_missing_field(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "krx" / "kospi_index" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "trade_date": "2024-01-02",
                "open_price": "2645.50",
                "high_price": "2660.00",
                "low_price": "2642.20",
                "volume": 1020000,
                "turnover": "852500000000.00",
            }
        ],
    )

    silver_normalizer = SilverNormalizer(output_root=tmp_path / "silver")

    with pytest.raises(MissingFieldError, match="close_price"):
        _ = silver_normalizer.normalize_parquet(bronze_path)


def test_silver_normalizer_raises_typed_error_for_invalid_value(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "ecos" / "base_rate" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "ecos",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "value_date": "2024-01-02",
                "base_rate": "not-a-number",
            }
        ],
    )

    silver_normalizer = SilverNormalizer(output_root=tmp_path / "silver")

    with pytest.raises(InvalidValueError, match="base_rate"):
        _ = silver_normalizer.normalize_parquet(bronze_path)


def test_silver_normalizer_raises_typed_error_for_non_trading_day(tmp_path: Path) -> None:
    bronze_ingestor = BronzeIngestor(
        output_root=tmp_path / "bronze",
        deterministic_run_timestamp=RUN_TIMESTAMP,
    )
    bronze_result = bronze_ingestor.ingest(
        connector=FixtureKrxConnector(FIXTURES_ROOT),
        dataset_id="kospi_index",
        start=date(2024, 1, 1),
        end=date(2024, 1, 1),
    )

    silver_normalizer = SilverNormalizer(output_root=tmp_path / "silver")

    with pytest.raises(NonTradingDayError, match="2024-01-01"):
        _ = silver_normalizer.normalize_ingest_result(bronze_result)


def test_silver_normalizer_is_deterministic_for_identical_bronze_input(tmp_path: Path) -> None:
    bronze_ingestor = BronzeIngestor(
        output_root=tmp_path / "bronze",
        deterministic_run_timestamp=RUN_TIMESTAMP,
    )
    bronze_result = bronze_ingestor.ingest(
        connector=FixtureKrxConnector(FIXTURES_ROOT),
        dataset_id="investor_flow",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )

    first_normalizer = SilverNormalizer(output_root=tmp_path / "silver-one")
    second_normalizer = SilverNormalizer(output_root=tmp_path / "silver-two")

    first_paths = first_normalizer.normalize_ingest_result(bronze_result)
    second_paths = second_normalizer.normalize_ingest_result(bronze_result)

    assert [_read_rows(path) for path in first_paths] == [_read_rows(path) for path in second_paths]
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in first_paths] == [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in second_paths
    ]


def test_trading_calendar_rejects_unsupported_year() -> None:
    calendar = TradingCalendar()

    with pytest.raises(ValueError, match="2027"):
        _ = calendar.is_trading_day(date(2027, 1, 2))


def test_silver_normalizer_rejects_unsupported_dataset(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "krx" / "unsupported" / "2024-01-02.parquet"
    _write_bronze_partition(bronze_path, [{"source_name": "krx"}])

    with pytest.raises(ValueError, match="unsupported Silver dataset"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_silver_normalizer_normalize_dataset_skips_missing_dates(tmp_path: Path) -> None:
    bronze_ingestor = BronzeIngestor(
        output_root=tmp_path / "bronze",
        deterministic_run_timestamp=RUN_TIMESTAMP,
    )
    _ = bronze_ingestor.ingest(
        connector=FixtureKrxConnector(FIXTURES_ROOT),
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )

    written_paths = SilverNormalizer(output_root=tmp_path / "silver").normalize_dataset(
        bronze_root=tmp_path / "bronze",
        source_name="krx",
        dataset_id="kospi_index",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )

    assert written_paths == (tmp_path / "silver" / "kospi_index" / "2024-01-02.parquet",)


def test_silver_normalizer_rejects_partition_date_mismatch(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "krx" / "kospi_index" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "trade_date": "2024-01-03",
                "open_price": "2645.50",
                "high_price": "2660.00",
                "low_price": "2642.20",
                "close_price": "2658.10",
                "volume": 1020000,
                "turnover": "852500000000.00",
            }
        ],
    )

    with pytest.raises(InvalidValueError, match="as_of_date"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_silver_normalizer_rejects_invalid_bronze_partition_path(tmp_path: Path) -> None:
    bronze_path = Path("2024-01-02.parquet")

    with pytest.raises(ValueError, match="invalid Bronze parquet path"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_assert_no_forbidden_columns_rejects_target_prefix() -> None:
    with pytest.raises(ValueError, match="target_feature"):
        assert_no_forbidden_columns(["as_of_date", "target_feature"])


def test_silver_normalizer_rejects_empty_text_field(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "ecos" / "base_rate" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "value_date": "2024-01-02",
                "base_rate": "3.50",
            }
        ],
    )

    with pytest.raises(InvalidValueError, match="source_name"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_silver_normalizer_rejects_invalid_date_value(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "ecos" / "base_rate" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "ecos",
                "source_series_id": "base_rate",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "value_date": "not-a-date",
                "base_rate": "3.50",
            }
        ],
    )

    with pytest.raises(InvalidValueError, match="value_date"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_silver_normalizer_rejects_invalid_int_value(tmp_path: Path) -> None:
    bronze_path = tmp_path / "bronze" / "krx" / "kospi_index" / "2024-01-02.parquet"
    _write_bronze_partition(
        bronze_path,
        [
            {
                "source_name": "krx",
                "source_series_id": "kospi_index",
                "fetched_at": "2024-01-10T09:00:00+00:00",
                "trade_date": "2024-01-02",
                "open_price": "2645.50",
                "high_price": "2660.00",
                "low_price": "2642.20",
                "close_price": "2658.10",
                "volume": "not-an-int",
                "turnover": "852500000000.00",
            }
        ],
    )

    with pytest.raises(InvalidValueError, match="volume"):
        _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)


def test_silver_sha256_matches_file_bytes(tmp_path: Path) -> None:
    bronze_ingestor = BronzeIngestor(
        output_root=tmp_path / "bronze",
        deterministic_run_timestamp=RUN_TIMESTAMP,
    )
    bronze_result = bronze_ingestor.ingest(
        connector=FixtureKrxConnector(FIXTURES_ROOT),
        dataset_id="investor_flow",
        start=date(2024, 1, 2),
        end=date(2024, 1, 2),
    )
    silver_path = SilverNormalizer(output_root=tmp_path / "silver").normalize_ingest_result(
        bronze_result
    )[0]

    assert silver_sha256(silver_path) == hashlib.sha256(silver_path.read_bytes()).hexdigest()


def test_dataset_registry_covers_required_issue_datasets() -> None:
    assert set(DATASET_DEFINITIONS) >= {
        ("krx", "kospi_index"),
        ("krx", "investor_flow"),
        ("ecos", "base_rate"),
        ("kosis", "per_pbr_percentiles"),
    }


def test_silver_normalizer_rejects_non_date_as_of_date(tmp_path: Path) -> None:
    original_definition = DATASET_DEFINITIONS[("krx", "kospi_index")]
    DATASET_DEFINITIONS[("krx", "kospi_index")] = DatasetDefinition(
        normalize_row=lambda _raw_row: {
            "as_of_date": "2024-01-02",
            "source_name": "krx",
            "source_series_id": "kospi_index",
            "fetched_at": "2024-01-10T09:00:00+00:00",
        }
    )
    bronze_path = tmp_path / "bronze" / "krx" / "kospi_index" / "2024-01-02.parquet"
    _write_bronze_partition(bronze_path, [{"source_name": "krx"}])

    try:
        with pytest.raises(InvalidValueError, match="as_of_date"):
            _ = SilverNormalizer(output_root=tmp_path / "silver").normalize_parquet(bronze_path)
    finally:
        DATASET_DEFINITIONS[("krx", "kospi_index")] = original_definition
