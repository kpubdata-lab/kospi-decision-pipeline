from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import os
from typing import Callable, Mapping, Protocol, cast, final, runtime_checkable
from urllib.parse import urlencode

import httpx

from ._http import HttpRequestError, HttpRetryPolicy, SyncHttpRequester
from ._secrets import resolve_live_api_key
from .base import ConnectorRowBase
from .base import SourceMetadata


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


_KOSIS_API_BASE_URL = "https://kosis.kr"
_KOSIS_API_PATH = "/openapi/Param/statisticsParameterData.do"
_KOSIS_API_METHOD = "getList"
_KOSIS_API_FORMAT = "json"
_KOSIS_JSON_VD = "Y"
_KOSIS_API_VERSION = "getList"
_LIVE_CONNECTOR_ID = "kospi_decision_pipeline_app_kr_kospi.connectors.kosis.LiveKosisConnector"


@dataclass(frozen=True, slots=True)
class _KosisSeriesDefinition:
    dataset_name: str
    org_id: str
    table_id: str
    item_id: str
    object_level_1: str
    period_type: str
    series_name: str
    unit: str


_MACRO_INDICATORS_SERIES = _KosisSeriesDefinition(
    dataset_name="macro_indicators",
    org_id="101",
    table_id="DT_1J22003",
    item_id="T",
    object_level_1="T10",
    period_type="M",
    series_name="T10",
    unit="",
)


@final
class LiveKosisConnector:
    _api_key: str
    _key_fingerprint_sha256: str
    _http_requester: SyncHttpRequester
    _environment: Mapping[str, str]
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
        self._environment = environment or os.environ
        self._api_key = cast(
            str,
            resolve_live_api_key(
                source="kosis",
                api_key=api_key,
                environment=self._environment,
            ),
        )
        self._key_fingerprint_sha256 = hashlib.sha256(self._api_key.encode("utf-8")).hexdigest()[
            :16
        ]
        self._http_requester = SyncHttpRequester(retry_policy, sleep=sleep or _default_sleep)
        self._transport = transport
        self._now = now or _utc_now

    def fetch_per_pbr_percentiles(self, start: date, end: date) -> tuple[PerPbrPercentileRow, ...]:
        del start, end
        raise ValueError(
            "KOSIS live ingest does not support per_pbr_percentiles in v0.2; "
            "only bronze macro_indicators is supported"
        )

    def fetch_macro_indicators(self, start: date, end: date) -> tuple[KosisMacroIndicatorRow, ...]:
        payload = self._fetch_payload(_MACRO_INDICATORS_SERIES, start, end)
        return parse_macro_indicator_rows(
            payload=payload,
            dataset_name=_MACRO_INDICATORS_SERIES.dataset_name,
            fetched_at_utc=self._fetched_at_utc(),
            key_fingerprint_sha256=self._key_fingerprint_sha256,
            series_name=_MACRO_INDICATORS_SERIES.series_name,
            unit=_MACRO_INDICATORS_SERIES.unit,
        )

    def _fetch_payload(self, definition: _KosisSeriesDefinition, start: date, end: date) -> object:
        params = {
            "method": _KOSIS_API_METHOD,
            "apiKey": self._api_key,
            "format": _KOSIS_API_FORMAT,
            "jsonVD": _KOSIS_JSON_VD,
            "orgId": definition.org_id,
            "tblId": definition.table_id,
            "itmId": definition.item_id,
            "objL1": definition.object_level_1,
            "prdSe": definition.period_type,
            "startPrdDe": _format_period(start, definition.period_type),
            "endPrdDe": _format_period(end, definition.period_type),
        }
        path = f"{_KOSIS_API_PATH}?{urlencode(params)}"
        try:
            with httpx.Client(
                base_url=_KOSIS_API_BASE_URL,
                timeout=httpx.Timeout(self._http_requester.retry_policy.timeout_seconds),
                transport=self._transport,
            ) as client:
                return self._http_requester.get(client, path)
        except HttpRequestError as error:
            message = str(error)
            if message.startswith("HTTP 401") or message.startswith("HTTP 403"):
                raise PermissionError(f"KOSIS authentication failed: {message}") from error
            raise

    def _fetched_at_utc(self) -> str:
        return self._now().replace(microsecond=0).isoformat()


def parse_macro_indicator_rows(
    *,
    payload: object,
    dataset_name: str,
    fetched_at_utc: str,
    key_fingerprint_sha256: str,
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
    dataset_name: str, fetched_at_utc: str, key_fingerprint_sha256: str
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
    if not isinstance(payload, list):
        raise ValueError("KOSIS payload must be a JSON array")
    rows: list[Mapping[str, object]] = []
    for raw_row in cast(list[object], payload):
        if not isinstance(raw_row, dict):
            raise ValueError("KOSIS row payload must be a JSON object")
        rows.append(cast(dict[str, object], raw_row))
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


def _format_period(value: date, period_type: str) -> str:
    if period_type != "M":
        raise ValueError(f"unsupported KOSIS period type: {period_type}")
    return value.strftime("%Y%m")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_sleep(seconds: float) -> None:
    from time import sleep

    sleep(seconds)
