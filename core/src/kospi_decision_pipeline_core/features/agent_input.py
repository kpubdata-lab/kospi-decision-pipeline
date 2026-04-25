from __future__ import annotations

from collections.abc import Mapping
from typing import Union

from .leakage_guard import LeakageError, assert_no_forbidden_columns

FeatureValue = Union[float, int, str]


def build_agent_feature_row(
    gold_row: Mapping[str, FeatureValue],
    allowed_columns: tuple[str, ...],
) -> dict[str, FeatureValue]:
    assert_no_forbidden_columns(gold_row.keys())
    assert_no_forbidden_columns(allowed_columns)

    non_whitelisted_columns = sorted(set(gold_row) - set(allowed_columns))
    if non_whitelisted_columns:
        raise LeakageError(f"non-whitelisted columns detected: {non_whitelisted_columns}")

    return {column: gold_row[column] for column in allowed_columns if column in gold_row}


__all__ = ["FeatureValue", "build_agent_feature_row"]
