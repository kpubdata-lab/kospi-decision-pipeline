from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import ClassVar, cast

import yaml

from ..schemas.decisions import AgentVote, DecisionResult, ModelLabel


@dataclass(frozen=True, slots=True)
class DecisionAgent:
    threshold_up: float
    threshold_down: float
    config_signature: str

    AGENT_NAME: ClassVar[str] = "decision"

    def decide(
        self,
        *,
        decision_date: date,
        votes: Sequence[AgentVote],
        snapshot_id: str,
    ) -> DecisionResult:
        votes_sorted = _sorted_unique_votes(votes)
        aggregate_score = sum(vote.weight * _signed(vote.label) for vote in votes_sorted)
        return DecisionResult(
            decision_date=decision_date,
            label=_decision_label(
                aggregate_score=aggregate_score,
                threshold_up=self.threshold_up,
                threshold_down=self.threshold_down,
            ),
            aggregate_score=aggregate_score,
            threshold_up=self.threshold_up,
            threshold_down=self.threshold_down,
            votes=votes_sorted,
            config_signature=self.config_signature,
            snapshot_id=snapshot_id,
        )


def compute_config_signature(yaml_path: Path) -> str:
    canonical_payload = cast(object, yaml.safe_load(yaml_path.read_text(encoding="utf-8")))
    canonical_text = yaml.safe_dump(
        canonical_payload,
        default_flow_style=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def _sorted_unique_votes(votes: Sequence[AgentVote]) -> tuple[AgentVote, ...]:
    if len(votes) == 0:
        raise ValueError("at least one vote required")

    votes_sorted = tuple(sorted(votes, key=lambda vote: vote.agent_name))
    for index in range(1, len(votes_sorted)):
        previous_vote = votes_sorted[index - 1]
        current_vote = votes_sorted[index]
        if previous_vote.agent_name == current_vote.agent_name:
            raise ValueError(f"duplicate agent_name: {current_vote.agent_name}")
    return votes_sorted


def _signed(label: ModelLabel) -> int:
    if label == "up":
        return 1
    if label == "down":
        return -1
    return 0


def _decision_label(
    *,
    aggregate_score: float,
    threshold_up: float,
    threshold_down: float,
) -> ModelLabel:
    if aggregate_score > threshold_up:
        return "up"
    if aggregate_score < threshold_down:
        return "down"
    return "skip"


__all__ = ["DecisionAgent", "compute_config_signature"]
