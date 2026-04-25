from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite, nan
from types import MappingProxyType
from typing import ClassVar, Literal

from ..features.leakage_guard import (
    LeakageError,
    assert_no_forbidden_columns,
)
from ..schemas import AgentRuleConfig, AgentVote, EvidenceItem

EXPECTED_RULE_VERSION = "volatility@1.0.0"
_COMPUTED_SOURCE = "computed"


@dataclass(frozen=True, slots=True)
class AgentFeatureRow:
    as_of: date
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", self.as_of)
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class VolatilityAgent:
    rule_config: AgentRuleConfig
    weight: float

    AGENT_NAME: ClassVar[str] = "volatility"
    INPUT_WHITELIST: ClassVar[tuple[str, ...]] = (
        "kospi_realized_vol_20d",
        "kospi_realized_vol_20d_percentile_252d",
        "kospi_atr_14d",
    )

    def __post_init__(self) -> None:
        if self.rule_config.rule_version != EXPECTED_RULE_VERSION:
            raise ValueError(f"rule_version must equal {EXPECTED_RULE_VERSION}")
        if isinstance(self.weight, bool):
            raise ValueError("weight must be a float")
        object.__setattr__(self, "weight", float(self.weight))

    def vote(self, row: AgentFeatureRow) -> AgentVote:
        feature_values = self._extract_feature_values(row)
        label, score = self._classify(feature_values)
        evidence = tuple(
            EvidenceItem(
                name=name, value=feature_values[name], source=_COMPUTED_SOURCE, as_of=row.as_of
            )
            for name in self.INPUT_WHITELIST
        )
        return AgentVote(
            agent_name=self.AGENT_NAME,
            rule_version=self.rule_config.rule_version,
            label=label,
            score=score,
            weight=self.weight,
            weighted_score=score * self.weight,
            evidence=evidence,
        )

    def _extract_feature_values(self, row: AgentFeatureRow) -> dict[str, float]:
        assert_no_forbidden_columns(row.values.keys())
        non_whitelisted_columns = sorted(set(row.values) - set(self.INPUT_WHITELIST))
        if non_whitelisted_columns:
            raise LeakageError(f"non-whitelisted columns detected: {non_whitelisted_columns}")
        return {
            name: self._coerce_feature_value(name, row.values.get(name))
            for name in self.INPUT_WHITELIST
        }

    def _coerce_feature_value(self, feature_name: str, raw_value: object) -> float:
        if raw_value is None:
            return nan
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise LeakageError(f"unsupported feature value for '{feature_name}': {raw_value!r}")
        return float(raw_value)

    def _classify(
        self, feature_values: Mapping[str, float]
    ) -> tuple[Literal["up", "down", "skip"], float]:
        rv20d = feature_values["kospi_realized_vol_20d"]
        rv_pct = feature_values["kospi_realized_vol_20d_percentile_252d"]
        atr14 = feature_values["kospi_atr_14d"]
        thresholds = self.rule_config.thresholds

        if (
            self._lte(rv20d, thresholds["realized_vol_20d_up_max"])
            and self._lte(rv_pct, thresholds["realized_vol_pct_up_max"])
            and self._lte(atr14, thresholds["atr_14d_up_max"])
        ):
            return ("up", 0.40)

        if self._gte(rv_pct, thresholds["realized_vol_pct_down_min"]) and (
            self._gte(rv20d, thresholds["realized_vol_20d_down_min"])
            or self._gte(atr14, thresholds["atr_14d_down_min"])
        ):
            return ("down", -0.65)

        if self._gt(rv_pct, thresholds["realized_vol_pct_mid_low"]) and self._lt(
            rv_pct, thresholds["realized_vol_pct_mid_high"]
        ):
            return ("skip", 0.0)

        return ("skip", 0.0)

    def _lte(self, value: float, threshold: float) -> bool:
        return isfinite(value) and value <= threshold

    def _gte(self, value: float, threshold: float) -> bool:
        return isfinite(value) and value >= threshold

    def _gt(self, value: float, threshold: float) -> bool:
        return isfinite(value) and value > threshold

    def _lt(self, value: float, threshold: float) -> bool:
        return isfinite(value) and value < threshold
