from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from typing import Protocol, TypedDict, cast, final, runtime_checkable

from kpubdata import Client
from kpubdata.core.models import Query

from .base import ConnectorRowBase, SourceMetadata


@dataclass(frozen=True, slots=True)
class EcosBaseRateRow(ConnectorRowBase):
    value_date: date
    base_rate: Decimal


@dataclass(frozen=True, slots=True)
class EcosUsdKrwRow(ConnectorRowBase):
    value_date: date
    exchange_rate: Decimal


@dataclass(frozen=True, slots=True)
class EcosBondYieldRow(ConnectorRowBase):
    value_date: date
    maturity_code: str
    yield_rate: Decimal


@runtime_checkable
class EcosConnector(Protocol):
    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]: ...

    def fetch_usd_krw_series(self, start: date, end: date) -> tuple[EcosUsdKrwRow, ...]: ...

    def fetch_bond_yield_series(self, start: date, end: date) -> tuple[EcosBondYieldRow, ...]: ...


_ECOS_API_VERSION = "StatisticSearch"
_ECOS_DAILY_CYCLE = "D"
_LIVE_CONNECTOR_ID = "kospi_decision_pipeline_app_kr_kospi.connectors.ecos.LiveEcosConnector"


class _EcosResponseRow(TypedDict):
    TIME: str
    DATA_VALUE: str


class _BatchLike(Protocol):
    items: Sequence[Mapping[str, object]]


@final
class LiveEcosConnector:
    _client: Client
    _key_fingerprint_sha256: str | None
    _now: Callable[[], datetime]

    def __init__(self, *, client: Client, now: Callable[[], datetime] | None = None) -> None:
        self._client = client
        self._key_fingerprint_sha256 = _provider_key_fingerprint_sha256(client, "bok")
        self._now = now or _utc_now

    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]:
        rows = self._query_series("bok.base_rate", start, end)
        return parse_base_rate_rows(rows, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def fetch_usd_krw_series(self, start: date, end: date) -> tuple[EcosUsdKrwRow, ...]:
        rows = self._query_series("bok.usd_krw", start, end)
        return parse_usd_krw_rows(rows, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def fetch_bond_yield_series(self, start: date, end: date) -> tuple[EcosBondYieldRow, ...]:
        rows = self._query_series("bok.bond_yield_3y", start, end)
        return parse_bond_yield_rows(rows, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def _query_series(
        self,
        dataset_id: str,
        start: date,
        end: date,
    ) -> tuple[Mapping[str, object], ...]:
        batch = _query_record_batch(
            dataset=self._client.dataset(dataset_id),
            query=Query(
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                extra={"frequency": _ECOS_DAILY_CYCLE},
            ),
        )
        return tuple(batch.items)

    def _fetched_at_utc(self) -> str:
        return self._now().replace(microsecond=0).isoformat()


def parse_base_rate_rows(
    payload: object,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
) -> tuple[EcosBaseRateRow, ...]:
    metadata = _source_metadata("base_rate", fetched_at_utc, key_fingerprint_sha256)
    return tuple(
        sorted(
            (
                EcosBaseRateRow(
                    metadata=metadata,
                    value_date=_parse_ecos_date(raw_row["TIME"]),
                    base_rate=_parse_decimal(raw_row["DATA_VALUE"]),
                )
                for raw_row in _ecos_rows(payload)
            ),
            key=lambda row: row.value_date,
        )
    )


def parse_usd_krw_rows(
    payload: object,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
) -> tuple[EcosUsdKrwRow, ...]:
    metadata = _source_metadata("usd_krw", fetched_at_utc, key_fingerprint_sha256)
    return tuple(
        sorted(
            (
                EcosUsdKrwRow(
                    metadata=metadata,
                    value_date=_parse_ecos_date(raw_row["TIME"]),
                    exchange_rate=_parse_decimal(raw_row["DATA_VALUE"]),
                )
                for raw_row in _ecos_rows(payload)
            ),
            key=lambda row: row.value_date,
        )
    )


def parse_bond_yield_rows(
    payload: object,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
) -> tuple[EcosBondYieldRow, ...]:
    metadata = _source_metadata("bond_yield", fetched_at_utc, key_fingerprint_sha256)
    return tuple(
        sorted(
            (
                EcosBondYieldRow(
                    metadata=metadata,
                    value_date=_parse_ecos_date(raw_row["TIME"]),
                    maturity_code="3Y",
                    yield_rate=_parse_decimal(raw_row["DATA_VALUE"]),
                )
                for raw_row in _ecos_rows(payload)
            ),
            key=lambda row: row.value_date,
        )
    )


def _source_metadata(
    dataset_name: str,
    fetched_at_utc: str,
    key_fingerprint_sha256: str | None,
) -> SourceMetadata:
    return SourceMetadata(
        source_name="ecos",
        dataset_name=dataset_name,
        fetched_at_utc=fetched_at_utc,
        connector_id=_LIVE_CONNECTOR_ID,
        api_version=_ECOS_API_VERSION,
        key_fingerprint_sha256=key_fingerprint_sha256,
    )


def _ecos_rows(payload: object) -> tuple[_EcosResponseRow, ...]:
    rows: list[_EcosResponseRow] = []
    for raw_row in _require_record_sequence(payload, "ECOS record batch payload"):
        rows.append(
            {
                "TIME": _require_string(raw_row, "TIME"),
                "DATA_VALUE": _require_string(raw_row, "DATA_VALUE"),
            }
        )
    return tuple(rows)


def _require_record_sequence(
    payload: object,
    message: str,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        raise ValueError(message)
    raw_payload = cast(Sequence[object], payload)
    rows: list[Mapping[str, object]] = []
    for raw_row in raw_payload:
        if not isinstance(raw_row, Mapping):
            raise ValueError("ECOS record payload must be an object")
        rows.append(cast(Mapping[str, object], raw_row))
    return tuple(rows)


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing ECOS string field: {key}")
    return value


def _parse_ecos_date(value: str) -> date:
    return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-{value[6:8]}")


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value)


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


def _query_record_batch(dataset: object, query: Query) -> _BatchLike:
    query_records = getattr(dataset, "query_records", None)
    if callable(query_records):
        return cast(_BatchLike, query_records(query))

    list_records = getattr(dataset, "list", None)
    if callable(list_records):
        list_kwargs: dict[str, object] = {
            "start_date": query.start_date,
            "end_date": query.end_date,
            "frequency": cast(str, query.extra["frequency"]),
        }
        return cast(_BatchLike, list_records(**list_kwargs))

    raise TypeError("kpubdata dataset must provide query_records(Query) or list(...)")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
