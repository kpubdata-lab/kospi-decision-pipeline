from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite, nan
from typing import ClassVar, Literal

from kospi_decision_pipeline_core.features.agent_input import build_agent_feature_row
from kospi_decision_pipeline_core.schemas.config import AgentRuleConfig
from kospi_decision_pipeline_core.schemas.decisions import AgentVote, EvidenceItem

AgentFeatureRow = Mapping[str, object]

_EVIDENCE_ORDER: tuple[str, ...] = (
    "kospi_ma5_gap",
    "kospi_close_position",
    "kospi_return_5d",
    "kospi_return_1d",
)
_EVIDENCE_SOURCE = "computed"
_EVIDENCE_AS_OF = date.min


@dataclass(frozen=True, slots=True)
class TechnicalAgent:
    rule_config: AgentRuleConfig
    weight: float

    AGENT_NAME: ClassVar[str] = "technical"
    INPUT_WHITELIST: ClassVar[tuple[str, ...]] = (
        "kospi_return_1d",
        "kospi_return_5d",
        "kospi_ma5_gap",
        "kospi_close_position",
    )

    def vote(self, row: AgentFeatureRow) -> AgentVote:
        raw_values = _extract_whitelisted_values(row, allowed_columns=self.INPUT_WHITELIST)
        return_1d = _finite_float_or_none(raw_values["kospi_return_1d"])
        return_5d = _finite_float_or_none(raw_values["kospi_return_5d"])
        ma5_gap = _finite_float_or_none(raw_values["kospi_ma5_gap"])
        close_position = _finite_float_or_none(raw_values["kospi_close_position"])

        label: Literal["up", "down", "skip"] = "skip"
        score = 0.0

        if any(value is None for value in (return_1d, return_5d, ma5_gap, close_position)):
            label = "skip"
            score = 0.0
        elif (
            ma5_gap is not None
            and close_position is not None
            and return_5d is not None
            and ma5_gap >= self._threshold("ma5_gap_up_min")
            and close_position >= self._threshold("close_position_up_min")
            and return_5d >= self._threshold("return_5d_up_min")
        ):
            label = "up"
            score = 0.70
        elif (
            ma5_gap is not None
            and close_position is not None
            and return_5d is not None
            and ma5_gap <= self._threshold("ma5_gap_down_max")
            and close_position <= self._threshold("close_position_down_max")
            and return_5d <= self._threshold("return_5d_down_max")
        ):
            label = "down"
            score = -0.70
        elif (
            return_1d is not None
            and return_5d is not None
            and ((return_1d > 0.0 and return_5d < 0.0) or (return_1d < 0.0 and return_5d > 0.0))
        ):
            label = "skip"
            score = 0.0

        return AgentVote(
            agent_name=self.AGENT_NAME,
            rule_version=self.rule_config.rule_version,
            label=label,
            score=score,
            weight=self.weight,
            weighted_score=score * self.weight,
            evidence=_build_evidence(raw_values),
        )

    def _threshold(self, name: str) -> float:
        threshold = self.rule_config.thresholds.get(name)
        if threshold is None:
            raise ValueError(f"missing threshold for technical rule: {name}")
        return threshold


def _extract_whitelisted_values(
    row: AgentFeatureRow,
    *,
    allowed_columns: tuple[str, ...],
) -> dict[str, object | None]:
    _ = build_agent_feature_row(_coerce_nulls_for_sanitizer(row), allowed_columns)
    return {column: row[column] if column in row else None for column in allowed_columns}


def _coerce_nulls_for_sanitizer(row: AgentFeatureRow) -> dict[str, object]:
    return {column: 0.0 if value is None else value for column, value in row.items()}


def _finite_float_or_none(value: object | None) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    numeric_value = float(value)
    if not isfinite(numeric_value):
        return None
    return numeric_value


def _evidence_value(value: object | None) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return nan
    return float(value)


def _build_evidence(raw_values: Mapping[str, object | None]) -> tuple[EvidenceItem, ...]:
    return tuple(
        EvidenceItem(
            name=name,
            value=_evidence_value(raw_values[name]),
            source=_EVIDENCE_SOURCE,
            as_of=_EVIDENCE_AS_OF,
        )
        for name in _EVIDENCE_ORDER
    )


__all__ = ["TechnicalAgent"]
