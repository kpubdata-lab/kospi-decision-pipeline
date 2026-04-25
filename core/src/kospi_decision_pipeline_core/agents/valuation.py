from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import ClassVar, TypeAlias

from kospi_decision_pipeline_core.schemas import (
    AgentRuleConfig,
    AgentVote,
    EvidenceItem,
    ModelLabel,
)

AgentFeatureRow: TypeAlias = Mapping[str, object]

_EVIDENCE_AS_OF = date(1970, 1, 1)
_EVIDENCE_SOURCES: tuple[tuple[str, str], ...] = (
    ("kospi_per", "KRX"),
    ("kospi_pbr", "KRX"),
    ("kospi_per_percentile_252d", "computed"),
    ("kospi_pbr_percentile_252d", "computed"),
)


@dataclass(frozen=True, slots=True)
class ValuationAgent:
    rule_config: AgentRuleConfig
    weight: float

    AGENT_NAME: ClassVar[str] = "valuation"
    INPUT_WHITELIST: ClassVar[tuple[str, ...]] = (
        "kospi_per",
        "kospi_pbr",
        "kospi_per_percentile_252d",
        "kospi_pbr_percentile_252d",
    )

    def vote(self, row: AgentFeatureRow) -> AgentVote:
        _validate_row(row, self.INPUT_WHITELIST)

        per = _read_feature(row, "kospi_per")
        pbr = _read_feature(row, "kospi_pbr")
        per_pct = _read_feature(row, "kospi_per_percentile_252d")
        pbr_pct = _read_feature(row, "kospi_pbr_percentile_252d")

        thresholds = self.rule_config.thresholds
        per_percentile_up_max = _read_threshold(thresholds, "per_percentile_up_max")
        pbr_percentile_up_max = _read_threshold(thresholds, "pbr_percentile_up_max")
        per_percentile_down_min = _read_threshold(thresholds, "per_percentile_down_min")
        pbr_percentile_down_min = _read_threshold(thresholds, "pbr_percentile_down_min")
        fair_value_center = _read_threshold(thresholds, "fair_value_center")
        fair_value_half_band = _read_threshold(thresholds, "fair_value_half_band")

        label: ModelLabel
        score: float
        if (
            _is_positive_finite(per)
            and _is_positive_finite(pbr)
            and _is_finite_at_most(per_pct, per_percentile_up_max)
            and _is_finite_at_most(pbr_pct, pbr_percentile_up_max)
        ):
            label = "up"
            score = 0.55
        elif (
            _is_positive_finite(per)
            and _is_positive_finite(pbr)
            and _is_finite_at_least(per_pct, per_percentile_down_min)
            and _is_finite_at_least(pbr_pct, pbr_percentile_down_min)
        ):
            label = "down"
            score = -0.55
        elif _is_fair_value_band_match(
            per_pct, fair_value_center, fair_value_half_band
        ) and _is_fair_value_band_match(
            pbr_pct,
            fair_value_center,
            fair_value_half_band,
        ):
            label = "skip"
            score = 0.0
        else:
            label = "skip"
            score = 0.0

        evidence = tuple(
            EvidenceItem(
                name=name, value=_read_feature(row, name), source=source, as_of=_EVIDENCE_AS_OF
            )
            for name, source in _EVIDENCE_SOURCES
        )
        weight = _ensure_numeric(self.weight, context="weight")
        return AgentVote(
            agent_name=self.AGENT_NAME,
            rule_version=self.rule_config.rule_version,
            label=label,
            score=score,
            weight=weight,
            weighted_score=score * weight,
            evidence=evidence,
        )


def _validate_row(row: AgentFeatureRow, whitelist: tuple[str, ...]) -> None:
    non_whitelisted_inputs = tuple(sorted(set(row) - set(whitelist)))
    if non_whitelisted_inputs:
        raise ValueError(f"non-whitelisted inputs: {non_whitelisted_inputs}")

    missing_required_inputs = tuple(name for name in whitelist if name not in row)
    if missing_required_inputs:
        raise ValueError(f"missing required inputs: {missing_required_inputs}")


def _read_feature(row: AgentFeatureRow, name: str) -> float:
    return _ensure_numeric(row[name], context=name)


def _read_threshold(thresholds: Mapping[str, float], name: str) -> float:
    return _ensure_numeric(thresholds[name], context=name)


def _ensure_numeric(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} must be numeric")
    return float(value)


def _is_positive_finite(value: float) -> bool:
    return isfinite(value) and value > 0.0


def _is_finite_at_most(value: float, ceiling: float) -> bool:
    return isfinite(value) and value <= ceiling


def _is_finite_at_least(value: float, floor: float) -> bool:
    return isfinite(value) and value >= floor


def _is_fair_value_band_match(value: float, center: float, half_band: float) -> bool:
    return isfinite(value) and abs(value - center) <= half_band


__all__ = ["AgentFeatureRow", "ValuationAgent"]
