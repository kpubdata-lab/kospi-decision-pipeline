from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import ClassVar

from kospi_decision_pipeline_core.features.agent_input import FeatureValue, build_agent_feature_row
from kospi_decision_pipeline_core.schemas import (
    AgentRuleConfig,
    AgentVote,
    EvidenceItem,
    ModelLabel,
)

type AgentFeatureRow = Mapping[str, FeatureValue]


@dataclass(frozen=True, slots=True)
class DomesticMacroAgent:
    rule_config: AgentRuleConfig
    weight: float

    AGENT_NAME: ClassVar[str] = "domestic_macro"
    INPUT_WHITELIST: ClassVar[tuple[str, ...]] = (
        "bok_base_rate_change_30d",
        "usd_krw_return_5d",
        "kr_bond_yield_change_30d",
    )

    def __post_init__(self) -> None:
        if not isfinite(self.weight):
            raise ValueError("weight must be finite")

    def vote(self, row: AgentFeatureRow) -> AgentVote:
        sanitized_row = build_agent_feature_row(row, self.INPUT_WHITELIST)

        bok_rate_change = _require_float_feature(sanitized_row, "bok_base_rate_change_30d")
        usdkrw_5d = _require_float_feature(sanitized_row, "usd_krw_return_5d")
        bond_change = _require_float_feature(sanitized_row, "kr_bond_yield_change_30d")

        evidence = (
            _make_evidence_item("bok_base_rate_change_30d", bok_rate_change),
            _make_evidence_item("usd_krw_return_5d", usdkrw_5d),
            _make_evidence_item("kr_bond_yield_change_30d", bond_change),
        )

        label: ModelLabel

        if _is_supportive(self.rule_config, bok_rate_change, usdkrw_5d, bond_change):
            label = "up"
            score = 0.60
        elif _is_risk_off(self.rule_config, bok_rate_change, usdkrw_5d, bond_change):
            label = "down"
            score = -0.70
        elif _is_conflicting(self.rule_config, usdkrw_5d, bond_change):
            label = "skip"
            score = 0.0
        else:
            label = "skip"
            score = 0.0

        return AgentVote(
            agent_name=self.AGENT_NAME,
            rule_version=self.rule_config.rule_version,
            label=label,
            score=score,
            weight=self.weight,
            weighted_score=self.weight * score,
            evidence=evidence,
        )


def _make_evidence_item(name: str, value: float) -> EvidenceItem:
    return EvidenceItem(name=name, value=value, source="computed", as_of=date.min)


def _require_float_feature(row: Mapping[str, FeatureValue], feature_name: str) -> float:
    if feature_name not in row:
        raise ValueError(f"missing required feature: {feature_name}")
    value = row[feature_name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{feature_name} must be numeric")
    return float(value)


def _threshold(rule_config: AgentRuleConfig, threshold_name: str) -> float:
    threshold_value = rule_config.thresholds.get(threshold_name)
    if threshold_value is None:
        raise ValueError(f"missing threshold: {threshold_name}")
    return float(threshold_value)


def _all_finite(*values: float) -> bool:
    return all(isfinite(value) for value in values)


def _is_supportive(
    rule_config: AgentRuleConfig,
    bok_rate_change: float,
    usdkrw_5d: float,
    bond_change: float,
) -> bool:
    if not _all_finite(bok_rate_change, usdkrw_5d, bond_change):
        return False
    return (
        bok_rate_change <= _threshold(rule_config, "bok_rate_change_up_max")
        and usdkrw_5d <= _threshold(rule_config, "usdkrw_return_5d_up_max")
        and bond_change <= _threshold(rule_config, "bond_yield_change_30d_up_max")
    )


def _is_risk_off(
    rule_config: AgentRuleConfig,
    bok_rate_change: float,
    usdkrw_5d: float,
    bond_change: float,
) -> bool:
    if not _all_finite(bok_rate_change, usdkrw_5d, bond_change):
        return False
    return bok_rate_change >= _threshold(rule_config, "bok_rate_change_down_min") or (
        usdkrw_5d >= _threshold(rule_config, "usdkrw_return_5d_down_min")
        and bond_change >= _threshold(rule_config, "bond_yield_change_30d_down_min")
    )


def _is_conflicting(
    rule_config: AgentRuleConfig,
    usdkrw_5d: float,
    bond_change: float,
) -> bool:
    if not _all_finite(usdkrw_5d, bond_change):
        return False
    return (
        usdkrw_5d >= _threshold(rule_config, "usdkrw_return_5d_mixed_pos_min")
        and bond_change < _threshold(rule_config, "bond_yield_change_30d_mixed_neg_max")
    ) or (
        usdkrw_5d <= _threshold(rule_config, "usdkrw_return_5d_mixed_neg_max")
        and bond_change > _threshold(rule_config, "bond_yield_change_30d_mixed_pos_min")
    )


__all__ = ["AgentFeatureRow", "DomesticMacroAgent"]
