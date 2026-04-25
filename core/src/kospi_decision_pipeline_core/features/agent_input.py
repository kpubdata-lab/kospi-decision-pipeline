from __future__ import annotations

from collections.abc import Mapping
from typing import Union

from .leakage_guard import LeakageError, assert_no_forbidden_columns

FeatureValue = Union[float, int, str]


def build_agent_feature_row(
    gold_row: Mapping[str, object],
    allowed_columns: tuple[str, ...],
) -> dict[str, FeatureValue]:
    assert_no_forbidden_columns(gold_row.keys())
    assert_no_forbidden_columns(allowed_columns)

    non_whitelisted_columns = sorted(set(gold_row) - set(allowed_columns))
    if non_whitelisted_columns:
        raise LeakageError(f"non-whitelisted columns detected: {non_whitelisted_columns}")

    sanitized_row: dict[str, FeatureValue] = {}
    for column in allowed_columns:
        if column not in gold_row:
            continue
        value = gold_row[column]
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise LeakageError(f"unsupported feature value for '{column}': {value!r}")
        sanitized_row[column] = value

    return sanitized_row


__all__ = ["FeatureValue", "build_agent_feature_row"]
