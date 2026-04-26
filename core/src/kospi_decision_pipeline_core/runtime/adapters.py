from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import cast

from abdp.agents import AgentContext, AgentDecision

from kospi_decision_pipeline_core.agents import (
    DecisionAgent,
    DomesticMacroAgent,
    FlowAgent,
    TechnicalAgent,
    ValuationAgent,
    VolatilityAgent,
)
from kospi_decision_pipeline_core.agents.domestic_macro import (
    AgentFeatureRow as DomesticMacroFeatureRow,
)
from kospi_decision_pipeline_core.agents.flow import AgentFeatureRow as FlowFeatureRow
from kospi_decision_pipeline_core.agents.technical import AgentFeatureRow as TechnicalFeatureRow
from kospi_decision_pipeline_core.agents.valuation import AgentFeatureRow as ValuationFeatureRow
from kospi_decision_pipeline_core.agents.volatility import AgentFeatureRow as VolatilityFeatureRow
from kospi_decision_pipeline_core.features.agent_input import FeatureValue

from .models import (
    DecisionResultProposal,
    KospiActionProposal,
    KospiDecisionParticipant,
    KospiDecisionSegment,
    ProposalBatch,
    VoteProposal,
)


@dataclass(slots=True)
class KospiAgentDecision:
    agent_id: str
    proposals: ProposalBatch


def _active_segment(
    context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
) -> KospiDecisionSegment:
    if len(context.state.segments) != 1:
        raise ValueError("expected exactly one scenario segment")
    return context.state.segments[0]


def _subset_features(row: dict[str, object], columns: tuple[str, ...]) -> dict[str, object]:
    return {column: row[column] for column in columns if column in row}


def _extract_as_of_date(row: dict[str, object]) -> date:
    raw_value = row.get("as_of_date", row.get("trade_date"))
    if not isinstance(raw_value, date):
        raise ValueError("features row must include as_of_date")
    return raw_value


@dataclass(slots=True)
class TechnicalAgentAdapter:
    agent: TechnicalAgent
    agent_id: str = TechnicalAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "vote":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        vote = self.agent.vote(
            cast(
                TechnicalFeatureRow,
                _feature_values_only(dict(segment.features_row), self.agent.INPUT_WHITELIST),
            )
        )
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(VoteProposal.from_vote(vote, step_index=context.step_index),),
        )


@dataclass(slots=True)
class DomesticMacroAgentAdapter:
    agent: DomesticMacroAgent
    agent_id: str = DomesticMacroAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "vote":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        vote = self.agent.vote(
            cast(
                DomesticMacroFeatureRow,
                _feature_values_only(dict(segment.features_row), self.agent.INPUT_WHITELIST),
            )
        )
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(VoteProposal.from_vote(vote, step_index=context.step_index),),
        )


@dataclass(slots=True)
class FlowAgentAdapter:
    agent: FlowAgent
    agent_id: str = FlowAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "vote":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        row = dict(segment.features_row)
        flow_row = FlowFeatureRow.from_mapping(
            {
                "as_of_date": _extract_as_of_date(row),
                **_subset_features(row, self.agent.INPUT_WHITELIST),
            }
        )
        vote = self.agent.vote(flow_row)
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(VoteProposal.from_vote(vote, step_index=context.step_index),),
        )


@dataclass(slots=True)
class ValuationAgentAdapter:
    agent: ValuationAgent
    agent_id: str = ValuationAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "vote":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        vote = self.agent.vote(
            cast(
                ValuationFeatureRow,
                _feature_values_only(dict(segment.features_row), self.agent.INPUT_WHITELIST),
            )
        )
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(VoteProposal.from_vote(vote, step_index=context.step_index),),
        )


@dataclass(slots=True)
class VolatilityAgentAdapter:
    agent: VolatilityAgent
    agent_id: str = VolatilityAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "vote":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        row = dict(segment.features_row)
        vote = self.agent.vote(
            VolatilityFeatureRow(
                as_of=_extract_as_of_date(row),
                values=_subset_features(row, self.agent.INPUT_WHITELIST),
            )
        )
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(VoteProposal.from_vote(vote, step_index=context.step_index),),
        )


@dataclass(slots=True)
class DecisionAgentAdapter:
    agent: DecisionAgent
    agent_id: str = DecisionAgent.AGENT_NAME

    def decide(
        self,
        context: AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
    ) -> AgentDecision[KospiActionProposal]:
        segment = _active_segment(context)
        if segment.phase != "decide":
            return KospiAgentDecision(agent_id=self.agent_id, proposals=())
        decision_result = self.agent.decide(
            decision_date=segment.decision_date,
            votes=segment.votes,
            snapshot_id=segment.snapshot_id,
        )
        return KospiAgentDecision(
            agent_id=self.agent_id,
            proposals=(
                DecisionResultProposal.from_decision_result(
                    decision_result,
                    step_index=context.step_index,
                ),
            ),
        )


__all__ = [
    "DecisionAgentAdapter",
    "DomesticMacroAgentAdapter",
    "FlowAgentAdapter",
    "KospiAgentDecision",
    "TechnicalAgentAdapter",
    "ValuationAgentAdapter",
    "VolatilityAgentAdapter",
]


def _feature_values_only(
    row: dict[str, object], columns: tuple[str, ...]
) -> dict[str, FeatureValue]:
    filtered: dict[str, FeatureValue] = {}
    for column in columns:
        value = row.get(column)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"{column} must be a feature value")
        filtered[column] = value
    return filtered
