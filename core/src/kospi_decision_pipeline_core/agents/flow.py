from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from kospi_decision_pipeline_core.schemas.config import AgentRuleConfig
from kospi_decision_pipeline_core.schemas.decisions import AgentVote


@dataclass(frozen=True, slots=True)
class AgentFeatureRow:
    as_of_date: date


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
        raise NotImplementedError
