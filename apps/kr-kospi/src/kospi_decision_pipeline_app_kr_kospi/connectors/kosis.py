from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from typing import Protocol, cast, final, runtime_checkable

from kpubdata import Client
from kpubdata.exceptions import DatasetNotFoundError

from .base import ConnectorRowBase, SourceMetadata


class UnsupportedDatasetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PerPbrPercentileRow(ConnectorRowBase):
    value_date: date
    per_percentile: Decimal
    pbr_percentile: Decimal


@dataclass(frozen=True, slots=True)
class KosisMacroIndicatorRow(ConnectorRowBase):
    value_date: date
    indicator_name: str
    indicator_value: Decimal
    unit: str


@runtime_checkable
class KosisConnector(Protocol):
    def fetch_per_pbr_percentiles(
        self, start: date, end: date
    ) -> tuple[PerPbrPercentileRow, ...]: ...

    def fetch_macro_indicators(
        self, start: date, end: date
    ) -> tuple[KosisMacroIndicatorRow, ...]: ...


_KOSIS_API_VERSION = "getList"
_LIVE_CONNECTOR_ID = "kospi_decision_pipeline_app_kr_kospi.connectors.kosis.LiveKosisConnector"


@final
class LiveKosisConnector:
    _client: Client
    _key_fingerprint_sha256: str | None
    _now: Callable[[], datetime]

    def __init__(self, *, client: Client, now: Callable[[], datetime] | None = None) -> None:
        self._client = client
        self._key_fingerprint_sha256 = _provider_key_fingerprint_sha256(client, "kosis")
        self._now = now or _utc_now

    def fetch_per_pbr_percentiles(self, start: date, end: date) -> tuple[PerPbrPercentileRow, ...]:
        del start, end
        raise UnsupportedDatasetError(
            "KOSIS live ingest does not support per_pbr_percentiles in v0.2; "
            "only bronze macro_indicators is supported"
        )

    def fetch_macro_indicators(self, start: date, end: date) -> tuple[KosisMacroIndicatorRow, ...]:
        try:
            batch = self._client.dataset("kosis.industrial_production").list(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
            )
        except DatasetNotFoundError as error:
            raise UnsupportedDatasetError(
                "KOSIS live ingest requires kpubdata dataset kosis.industrial_production"
            ) from error

        return parse_macro_indicator_rows(
            payload=cast(Sequence[Mapping[str, object]], batch.items),
            dataset_name="macro_indicators",
            fetched_at_utc=self._fetched_at_utc(),
            key_fingerprint_sha256=self._key_fingerprint_sha256,
            series_name="T10",
            unit="",
        )

    def _fetched_at_utc(self) -> str:
        return self._now().replace(microsecond=0).isoformat()


def parse_macro_indicator_rows(
    *,
    payload: object,
    dataset_name: str,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
    series_name: str,
    unit: str,
) -> tuple[KosisMacroIndicatorRow, ...]:
    metadata = _source_metadata(dataset_name, fetched_at_utc, key_fingerprint_sha256)
    rows: list[KosisMacroIndicatorRow] = []
    for raw_row in _kosis_rows(payload):
        indicator_name = _optional_string(raw_row, "C1_OBJ_NM") or series_name
        indicator_unit = _optional_string(raw_row, "UNIT_NM") or unit
        rows.append(
            KosisMacroIndicatorRow(
                metadata=metadata,
                value_date=_parse_kosis_period(_require_string(raw_row, "PRD_DE")),
                indicator_name=indicator_name,
                indicator_value=Decimal(_require_string(raw_row, "DT")),
                unit=indicator_unit,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.value_date))


def _source_metadata(
    dataset_name: str,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
) -> SourceMetadata:
    return SourceMetadata(
        source_name="kosis",
        dataset_name=dataset_name,
        fetched_at_utc=fetched_at_utc,
        connector_id=_LIVE_CONNECTOR_ID,
        api_version=_KOSIS_API_VERSION,
        key_fingerprint_sha256=key_fingerprint_sha256,
    )


def _kosis_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        raise ValueError("KOSIS record batch payload must be a sequence")
    raw_payload = cast(Sequence[object], payload)
    rows: list[Mapping[str, object]] = []
    for raw_row in raw_payload:
        if not isinstance(raw_row, Mapping):
            raise ValueError("KOSIS record payload must be an object")
        rows.append(cast(Mapping[str, object], raw_row))
    return tuple(rows)


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing KOSIS string field: {key}")
    return value


def _optional_string(mapping: Mapping[str, object], key: str) -> str | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if not isinstance(value, str):
        raise ValueError(f"missing KOSIS string field: {key}")
    return value


def _parse_kosis_period(value: str) -> date:
    if len(value) != 6:
        raise ValueError(f"unsupported KOSIS period format: {value}")
    return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-01")


def _provider_key_fingerprint_sha256(client: Client, provider: str) -> str | None:
    provider_keys = _provider_keys(client)
    if provider_keys is None:
        return None
    provider_key = provider_keys.get(provider)
    if not isinstance(provider_key, str) or provider_key == "":
        return None
    return hashlib.sha256(provider_key.encode("utf-8")).hexdigest()[:16]


def _provider_keys(client: Client) -> Mapping[str, str] | None:
    config = getattr(client, "_config", None)
    if config is None:
        return None
    provider_keys = getattr(config, "provider_keys", None)
    if not isinstance(provider_keys, Mapping):
        return None
    typed_provider_keys = cast(Mapping[object, object], provider_keys)
    typed_items: list[tuple[str, str]] = []
    for key, value in typed_provider_keys.items():
        if isinstance(key, str) and isinstance(value, str):
            typed_items.append((key, value))
    return dict(typed_items)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
