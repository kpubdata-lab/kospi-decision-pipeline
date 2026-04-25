from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import ClassVar

from kospi_decision_pipeline_core.features.leakage_guard import (
    LeakageError,
    assert_no_forbidden_columns,
)
from kospi_decision_pipeline_core.schemas.config import AgentRuleConfig
from kospi_decision_pipeline_core.schemas.decisions import AgentVote, EvidenceItem, ModelLabel


_AS_OF_DATE_COLUMN = "as_of_date"


@dataclass(frozen=True, slots=True)
class AgentFeatureRow:
    as_of_date: date
    foreign_net_buy_krw_5d_sum: float
    institution_net_buy_krw_5d_sum: float
    individual_net_buy_krw_5d_sum: float
    foreign_net_buy_5d_pct_of_turnover: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> AgentFeatureRow:
        assert_no_forbidden_columns(row.keys())
        allowed_columns = (_AS_OF_DATE_COLUMN,) + FlowAgent.INPUT_WHITELIST
        non_whitelisted_columns = sorted(set(row) - set(allowed_columns))
        if non_whitelisted_columns:
            raise LeakageError(f"non-whitelisted columns detected: {non_whitelisted_columns}")

        missing_columns = [column for column in allowed_columns if column not in row]
        if missing_columns:
            raise LeakageError(f"missing required columns: {missing_columns}")

        return cls(
            as_of_date=_require_date(row[_AS_OF_DATE_COLUMN], context=_AS_OF_DATE_COLUMN),
            foreign_net_buy_krw_5d_sum=_require_float_feature(
                row["foreign_net_buy_krw_5d_sum"],
                context="foreign_net_buy_krw_5d_sum",
            ),
            institution_net_buy_krw_5d_sum=_require_float_feature(
                row["institution_net_buy_krw_5d_sum"],
                context="institution_net_buy_krw_5d_sum",
            ),
            individual_net_buy_krw_5d_sum=_require_float_feature(
                row["individual_net_buy_krw_5d_sum"],
                context="individual_net_buy_krw_5d_sum",
            ),
            foreign_net_buy_5d_pct_of_turnover=_require_float_feature(
                row["foreign_net_buy_5d_pct_of_turnover"],
                context="foreign_net_buy_5d_pct_of_turnover",
            ),
        )


@dataclass(frozen=True, slots=True)
class FlowAgent:
    rule_config: AgentRuleConfig
    weight: float

    AGENT_NAME: ClassVar[str] = "flow"
    INPUT_WHITELIST: ClassVar[tuple[str, ...]] = (
        "foreign_net_buy_krw_5d_sum",
        "institution_net_buy_krw_5d_sum",
        "individual_net_buy_krw_5d_sum",
        "foreign_net_buy_5d_pct_of_turnover",
    )

    def vote(self, row: AgentFeatureRow) -> AgentVote:
        label: ModelLabel

        if self._matches_aligned_demand(row):
            label = "up"
            score = 0.80
        elif self._matches_aligned_distribution(row):
            label = "down"
            score = -0.80
        elif self._matches_divergent_or_weak_flow(row):
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
            weighted_score=score * self.weight,
            evidence=self._build_evidence(row),
        )

    def _matches_aligned_demand(self, row: AgentFeatureRow) -> bool:
        if not _all_finite(
            row.foreign_net_buy_krw_5d_sum,
            row.institution_net_buy_krw_5d_sum,
            row.individual_net_buy_krw_5d_sum,
            row.foreign_net_buy_5d_pct_of_turnover,
        ):
            return False

        return (
            row.foreign_net_buy_krw_5d_sum > 0.0
            and row.institution_net_buy_krw_5d_sum >= 0.0
            and row.individual_net_buy_krw_5d_sum <= 0.0
            and row.foreign_net_buy_5d_pct_of_turnover
            >= self.rule_config.thresholds["foreign_pct_up_min"]
        )

    def _matches_aligned_distribution(self, row: AgentFeatureRow) -> bool:
        if not _all_finite(
            row.foreign_net_buy_krw_5d_sum,
            row.institution_net_buy_krw_5d_sum,
            row.individual_net_buy_krw_5d_sum,
            row.foreign_net_buy_5d_pct_of_turnover,
        ):
            return False

        return (
            row.foreign_net_buy_krw_5d_sum < 0.0
            and row.institution_net_buy_krw_5d_sum <= 0.0
            and row.individual_net_buy_krw_5d_sum >= 0.0
            and row.foreign_net_buy_5d_pct_of_turnover
            <= self.rule_config.thresholds["foreign_pct_down_max"]
        )

    def _matches_divergent_or_weak_flow(self, row: AgentFeatureRow) -> bool:
        if not _all_finite(
            row.foreign_net_buy_krw_5d_sum,
            row.institution_net_buy_krw_5d_sum,
            row.foreign_net_buy_5d_pct_of_turnover,
        ):
            return False

        return (
            row.foreign_net_buy_krw_5d_sum * row.institution_net_buy_krw_5d_sum < 0.0
            or abs(row.foreign_net_buy_5d_pct_of_turnover)
            < self.rule_config.thresholds["foreign_pct_neutral_abs_max"]
        )

    def _build_evidence(self, row: AgentFeatureRow) -> tuple[EvidenceItem, ...]:
        return (
            EvidenceItem(
                name="foreign_net_buy_krw_5d_sum",
                value=row.foreign_net_buy_krw_5d_sum,
                source="KRX",
                as_of=row.as_of_date,
            ),
            EvidenceItem(
                name="institution_net_buy_krw_5d_sum",
                value=row.institution_net_buy_krw_5d_sum,
                source="KRX",
                as_of=row.as_of_date,
            ),
            EvidenceItem(
                name="individual_net_buy_krw_5d_sum",
                value=row.individual_net_buy_krw_5d_sum,
                source="KRX",
                as_of=row.as_of_date,
            ),
            EvidenceItem(
                name="foreign_net_buy_5d_pct_of_turnover",
                value=row.foreign_net_buy_5d_pct_of_turnover,
                source="computed",
                as_of=row.as_of_date,
            ),
        )


def _all_finite(*values: float) -> bool:
    return all(isfinite(value) for value in values)


def _require_date(value: object, *, context: str) -> date:
    if not isinstance(value, date):
        raise LeakageError(f"{context} must be a date")
    return value


def _require_float_feature(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LeakageError(f"{context} must be a float")
    return float(value)
