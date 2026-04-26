from __future__ import annotations

from dataclasses import replace
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from abdp.core.types import Seed
from abdp.scenario import ActionResolver
from abdp.simulation import ScenarioSpec, SimulationState, SnapshotRef

from kospi_decision_pipeline_core.schemas import AgentVote

from .models import (
    DecisionResultProposal,
    KospiActionProposal,
    KospiDecisionParticipant,
    KospiDecisionSegment,
    ScenarioPhase,
    VoteProposal,
)

RULE_AGENT_NAMES: tuple[str, ...] = (
    "technical",
    "domestic_macro",
    "flow",
    "valuation",
    "volatility",
)


class KospiNextDayScenario(
    ScenarioSpec[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]
):
    _scenario_key: str
    _decision_date: date
    _snapshot_id: str
    _features_row: dict[str, object]
    _seed: Seed
    _initial_phase: ScenarioPhase
    _votes: tuple[AgentVote, ...]
    _storage_key: str

    def __init__(
        self,
        *,
        scenario_id: str,
        decision_date: date,
        snapshot_id: str,
        features_row: dict[str, object],
        seed: Seed = Seed(17),
        initial_phase: ScenarioPhase = "vote",
        votes: tuple[AgentVote, ...] = (),
        storage_key: str | None = None,
    ) -> None:
        self._scenario_key = scenario_id
        self._decision_date = decision_date
        self._snapshot_id = snapshot_id
        self._features_row = dict(features_row)
        self._seed = seed
        self._initial_phase = initial_phase
        self._votes = votes
        self._storage_key = snapshot_id if storage_key is None else storage_key

    @property
    def scenario_key(self) -> str:
        return self._scenario_key

    @property
    def seed(self) -> Seed:
        return self._seed

    def build_initial_state(
        self,
    ) -> SimulationState[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]:
        participant = KospiDecisionParticipant(participant_id="market-kospi")
        segment = KospiDecisionSegment(
            segment_id="segment-kospi",
            participant_ids=(participant.participant_id,),
            phase=self._initial_phase,
            decision_date=self._decision_date,
            snapshot_id=self._snapshot_id,
            features_row=self._features_row,
            votes=self._votes,
            decision_result=None,
        )
        return SimulationState(
            step_index=0 if self._initial_phase == "vote" else 1,
            seed=self._seed,
            snapshot_ref=SnapshotRef(
                snapshot_id=uuid5(NAMESPACE_URL, self._snapshot_id),
                tier="gold",
                storage_key=self._storage_key,
            ),
            segments=(segment,),
            participants=(participant,),
            pending_actions=(),
        )


class KospiScenarioResolver(
    ActionResolver[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]
):
    def resolve(
        self,
        state: SimulationState[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
        proposals: tuple[KospiActionProposal, ...],
    ) -> SimulationState[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]:
        if len(state.segments) != 1:
            raise ValueError("expected exactly one scenario segment")
        segment = state.segments[0]
        if segment.phase == "vote":
            next_segment = self._resolve_vote_phase(segment, proposals)
        elif segment.phase == "decide":
            next_segment = self._resolve_decide_phase(segment, proposals)
        else:
            raise ValueError(f"cannot resolve terminal phase: {segment.phase}")
        return SimulationState(
            step_index=state.step_index + 1,
            seed=state.seed,
            snapshot_ref=state.snapshot_ref,
            segments=(next_segment,),
            participants=state.participants,
            pending_actions=(),
        )

    def _resolve_vote_phase(
        self,
        segment: KospiDecisionSegment,
        proposals: tuple[KospiActionProposal, ...],
    ) -> KospiDecisionSegment:
        if any(isinstance(proposal, DecisionResultProposal) for proposal in proposals):
            raise ValueError("vote phase must not receive DecisionResultProposal")
        vote_proposals = tuple(
            proposal for proposal in proposals if isinstance(proposal, VoteProposal)
        )
        unique_agent_names = {proposal.vote.agent_name for proposal in vote_proposals}
        if len(vote_proposals) != 5 or unique_agent_names != set(RULE_AGENT_NAMES):
            raise ValueError("vote phase requires exactly 5 unique VoteProposals")
        votes = tuple(
            sorted((proposal.vote for proposal in vote_proposals), key=lambda vote: vote.agent_name)
        )
        return replace(segment, phase="decide", votes=votes, decision_result=None)

    def _resolve_decide_phase(
        self,
        segment: KospiDecisionSegment,
        proposals: tuple[KospiActionProposal, ...],
    ) -> KospiDecisionSegment:
        decision_proposals = tuple(
            proposal for proposal in proposals if isinstance(proposal, DecisionResultProposal)
        )
        if len(decision_proposals) != 1 or len(proposals) != 1:
            raise ValueError("decide phase requires exactly 1 DecisionResultProposal")
        return replace(
            segment,
            phase="done",
            decision_result=decision_proposals[0].decision_result,
        )


__all__ = ["KospiNextDayScenario", "KospiScenarioResolver", "RULE_AGENT_NAMES"]
