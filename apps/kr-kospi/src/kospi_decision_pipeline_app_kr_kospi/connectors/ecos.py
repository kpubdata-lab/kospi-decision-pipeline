from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import os
from typing import Callable, Mapping, Protocol, TypedDict, cast, final, runtime_checkable

import httpx

from ._http import HttpRetryPolicy, SyncHttpRequester
from ._secrets import resolve_live_api_key
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


_ECOS_API_BASE_URL = "https://ecos.bok.or.kr"
_ECOS_RESULT_OK = "INFO-000"
_ECOS_FORMAT = "json"
_ECOS_LANGUAGE = "kr"
_ECOS_START_ROW = 1
_ECOS_END_ROW = 100000
_ECOS_DAILY_CYCLE = "D"
_ECOS_API_VERSION = "StatisticSearch"
_LIVE_CONNECTOR_ID = "kospi_decision_pipeline_app_kr_kospi.connectors.ecos.LiveEcosConnector"


@dataclass(frozen=True, slots=True)
class _EcosSeriesDefinition:
    stat_code: str
    item_code1: str


class _EcosResponseRow(TypedDict):
    TIME: str
    DATA_VALUE: str


_BASE_RATE_SERIES = _EcosSeriesDefinition(
    stat_code="722Y001",
    item_code1="0101000",
)
_USD_KRW_SERIES = _EcosSeriesDefinition(
    stat_code="731Y003",
    item_code1="0000003",
)
_BOND_YIELD_SERIES = _EcosSeriesDefinition(
    stat_code="817Y002",
    item_code1="010200000",
)


@final
class LiveEcosConnector:
    _api_key: str
    _key_fingerprint_sha256: str
    _http_requester: SyncHttpRequester
    _transport: httpx.BaseTransport | None
    _now: Callable[[], datetime]

    def __init__(
        self,
        api_key: str | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        retry_policy: HttpRetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._api_key = cast(
            str,
            resolve_live_api_key(
                source="ecos",
                api_key=api_key,
                environment=environment or os.environ,
            ),
        )
        self._key_fingerprint_sha256 = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()[
            :16
        ]
        self._http_requester = SyncHttpRequester(retry_policy, sleep=sleep or _default_sleep)
        self._transport = transport
        self._now = now or _utc_now

    def fetch_base_rate_series(self, start: date, end: date) -> tuple[EcosBaseRateRow, ...]:
        payload = self._fetch_payload(_BASE_RATE_SERIES, start, end)
        return parse_base_rate_rows(payload, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def fetch_usd_krw_series(self, start: date, end: date) -> tuple[EcosUsdKrwRow, ...]:
        payload = self._fetch_payload(_USD_KRW_SERIES, start, end)
        return parse_usd_krw_rows(payload, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def fetch_bond_yield_series(self, start: date, end: date) -> tuple[EcosBondYieldRow, ...]:
        payload = self._fetch_payload(_BOND_YIELD_SERIES, start, end)
        return parse_bond_yield_rows(payload, self._fetched_at_utc(), self._key_fingerprint_sha256)

    def _fetch_payload(self, definition: _EcosSeriesDefinition, start: date, end: date) -> object:
        path = _statistic_search_path(
            api_key=self._api_key,
            stat_code=definition.stat_code,
            start=start,
            end=end,
            item_code1=definition.item_code1,
        )
        with httpx.Client(
            base_url=_ECOS_API_BASE_URL,
            timeout=httpx.Timeout(self._http_requester.retry_policy.timeout_seconds),
            transport=self._transport,
        ) as client:
            return self._http_requester.get(client, path)

    def _fetched_at_utc(self) -> str:
        return self._now().replace(microsecond=0).isoformat()


def parse_base_rate_rows(
    payload: object, fetched_at_utc: str, key_fingerprint_sha256: str
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
    payload: object, fetched_at_utc: str, key_fingerprint_sha256: str
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
    payload: object, fetched_at_utc: str, key_fingerprint_sha256: str
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
    dataset_name: str, fetched_at_utc: str, key_fingerprint_sha256: str
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
    statistic_search = _require_nested_mapping(_require_payload_mapping(payload), "StatisticSearch")
    result = _require_nested_mapping(statistic_search, "RESULT")
    result_code = _require_string(result, "CODE")
    if result_code != _ECOS_RESULT_OK:
        message = _require_string(result, "MESSAGE")
        if "인증" in message or result_code.startswith("ERROR-3"):
            raise PermissionError(f"ECOS authentication failed: {result_code}: {message}")
        raise RuntimeError(f"ECOS request failed: {result_code}: {message}")
    raw_rows = statistic_search.get("row")
    if raw_rows is None:
        return ()
    rows: list[_EcosResponseRow] = []
    for raw_row in _require_object_list(raw_rows, "row"):
        mapping = _require_payload_mapping(raw_row)
        rows.append(
            {
                "TIME": _require_string(mapping, "TIME"),
                "DATA_VALUE": _require_string(mapping, "DATA_VALUE"),
            }
        )
    return tuple(rows)


def _require_payload_mapping(payload: object) -> Mapping[str, object]:
    if isinstance(payload, dict):
        return cast(dict[str, object], payload)
    raise ValueError("ECOS payload must be a JSON object")


def _require_nested_mapping(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    nested = mapping.get(key)
    if isinstance(nested, dict):
        return cast(dict[str, object], nested)
    raise ValueError(f"missing ECOS mapping field: {key}")


def _require_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing ECOS string field: {key}")
    return value


def _require_object_list(payload: object, key: str) -> tuple[object, ...]:
    if isinstance(payload, list):
        return tuple(cast(list[object], payload))
    raise ValueError(f"ECOS {key} payload must be a list")


def _parse_ecos_date(value: str) -> date:
    return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-{value[6:8]}")


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value)


def _statistic_search_path(
    *, api_key: str, stat_code: str, start: date, end: date, item_code1: str
) -> str:
    return (
        f"/api/StatisticSearch/{api_key}/{_ECOS_FORMAT}/{_ECOS_LANGUAGE}/"
        f"{_ECOS_START_ROW}/{_ECOS_END_ROW}/{stat_code}/{_ECOS_DAILY_CYCLE}/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}/{item_code1}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_sleep(seconds: float) -> None:
    from time import sleep

    sleep(seconds)
