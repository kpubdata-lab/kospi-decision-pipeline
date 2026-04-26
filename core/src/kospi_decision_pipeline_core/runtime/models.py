from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Literal, cast

from abdp.core.types import JsonObject

from kospi_decision_pipeline_core.schemas import AgentVote, DecisionResult
from kospi_decision_pipeline_core.schemas.serialization import to_jsonl_line

type ScenarioPhase = Literal["vote", "decide", "done"]


@dataclass(frozen=True, slots=True)
class KospiDecisionParticipant:
    participant_id: str


@dataclass(frozen=True, slots=True)
class KospiDecisionSegment:
    segment_id: str
    participant_ids: tuple[str, ...]
    phase: ScenarioPhase
    decision_date: date
    snapshot_id: str
    features_row: Mapping[str, object]
    votes: tuple[AgentVote, ...] = ()
    decision_result: DecisionResult | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "features_row", MappingProxyType(dict(self.features_row)))


@dataclass(frozen=True, slots=True)
class VoteProposal:
    proposal_id: str
    actor_id: str
    vote: AgentVote

    action_key: Literal["vote"] = "vote"

    @property
    def payload(self) -> JsonObject:
        return {"vote": cast(JsonObject, json.loads(to_jsonl_line(self.vote)))}

    @classmethod
    def from_vote(cls, vote: AgentVote, *, step_index: int) -> VoteProposal:
        return cls(
            proposal_id=f"vote:{vote.agent_name}:step{step_index}",
            actor_id=vote.agent_name,
            vote=vote,
        )


@dataclass(frozen=True, slots=True)
class DecisionResultProposal:
    proposal_id: str
    actor_id: str
    decision_result: DecisionResult

    action_key: Literal["decision_result"] = "decision_result"

    @property
    def payload(self) -> JsonObject:
        return {
            "decision_result": cast(JsonObject, json.loads(to_jsonl_line(self.decision_result)))
        }

    @classmethod
    def from_decision_result(
        cls,
        decision_result: DecisionResult,
        *,
        step_index: int,
    ) -> DecisionResultProposal:
        return cls(
            proposal_id=f"decision:step{step_index}:{decision_result.snapshot_id}",
            actor_id="decision",
            decision_result=decision_result,
        )


type KospiActionProposal = VoteProposal | DecisionResultProposal
type ProposalBatch = tuple[KospiActionProposal, ...]


__all__ = [
    "DecisionResultProposal",
    "KospiActionProposal",
    "KospiDecisionParticipant",
    "KospiDecisionSegment",
    "ProposalBatch",
    "ScenarioPhase",
    "VoteProposal",
]
