from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, final

import httpx


@dataclass(frozen=True, slots=True)
class HttpRetryPolicy:
    timeout_seconds: float = 10.0
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({500, 502, 503, 504})
    )


class HttpRequestError(RuntimeError):
    pass


@final
class SyncHttpRequester:
    _retry_policy: HttpRetryPolicy
    _sleep: Callable[[float], None]

    def __init__(
        self,
        retry_policy: HttpRetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._retry_policy = retry_policy or HttpRetryPolicy()
        self._sleep = sleep

    @property
    def retry_policy(self) -> HttpRetryPolicy:
        return self._retry_policy

    def get(self, client: httpx.Client, path: str) -> object:
        last_error: Exception | None = None
        for attempt in range(1, self._retry_policy.max_attempts + 1):
            try:
                response = client.get(path)
            except httpx.TransportError as error:
                last_error = error
                if attempt == self._retry_policy.max_attempts:
                    break
                self._sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code in self._retry_policy.retryable_status_codes:
                last_error = HttpRequestError(
                    f"HTTP {response.status_code} from upstream after attempt {attempt}"
                )
                if attempt == self._retry_policy.max_attempts:
                    break
                self._sleep(self._backoff_seconds(attempt))
                continue

            if response.status_code >= 400:
                raise HttpRequestError(f"HTTP {response.status_code} from upstream")

            return response.json()

        if last_error is None:
            raise HttpRequestError("HTTP request failed without response")
        raise HttpRequestError(
            f"HTTP request failed after {self._retry_policy.max_attempts} attempts"
        ) from last_error

    def _backoff_seconds(self, attempt: int) -> float:
        multiplier = 2 ** (attempt - 1)
        return float(self._retry_policy.backoff_base_seconds * multiplier)
