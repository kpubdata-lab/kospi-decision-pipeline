from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, TypeVar, cast


ModelLabel = Literal["up", "down", "skip"]
GroundTruthLabel = Literal["up", "down", "flat"]

_MODEL_LABELS = frozenset({"up", "down", "skip"})
_GROUND_TRUTH_LABELS = frozenset({"up", "down", "flat"})
_TupleItem = TypeVar("_TupleItem")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    name: str
    value: float
    source: str
    as_of: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_string(self.name, context="name"))
        object.__setattr__(self, "value", _ensure_float(self.value, context="value"))
        object.__setattr__(self, "source", _ensure_string(self.source, context="source"))
        object.__setattr__(self, "as_of", _ensure_date(self.as_of, context="as_of"))


@dataclass(frozen=True, slots=True)
class AgentVote:
    agent_name: str
    rule_version: str
    label: ModelLabel
    score: float
    weight: float
    weighted_score: float
    evidence: tuple[EvidenceItem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "agent_name",
            _ensure_string(self.agent_name, context="agent_name"),
        )
        object.__setattr__(
            self,
            "rule_version",
            _ensure_string(self.rule_version, context="rule_version"),
        )
        object.__setattr__(self, "label", _ensure_model_label(self.label, context="label"))
        object.__setattr__(self, "score", _ensure_float(self.score, context="score"))
        object.__setattr__(self, "weight", _ensure_float(self.weight, context="weight"))
        object.__setattr__(
            self,
            "weighted_score",
            _ensure_float(self.weighted_score, context="weighted_score"),
        )
        object.__setattr__(
            self,
            "evidence",
            _ensure_tuple_of(self.evidence, EvidenceItem, context="evidence"),
        )


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision_date: date
    label: ModelLabel
    aggregate_score: float
    threshold_up: float
    threshold_down: float
    votes: tuple[AgentVote, ...]
    config_signature: str
    snapshot_id: str

    def __post_init__(self) -> None:
        decision_date = _ensure_date(self.decision_date, context="decision_date")
        label = _ensure_model_label(self.label, context="label")
        aggregate_score = _ensure_float(self.aggregate_score, context="aggregate_score")
        threshold_up = _ensure_float(self.threshold_up, context="threshold_up")
        threshold_down = _ensure_float(self.threshold_down, context="threshold_down")
        if threshold_up <= threshold_down:
            raise ValueError("threshold_up must be greater than threshold_down")
        object.__setattr__(self, "decision_date", decision_date)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "aggregate_score", aggregate_score)
        object.__setattr__(self, "threshold_up", threshold_up)
        object.__setattr__(self, "threshold_down", threshold_down)
        object.__setattr__(self, "votes", _ensure_tuple_of(self.votes, AgentVote, context="votes"))
        object.__setattr__(
            self,
            "config_signature",
            _ensure_string(self.config_signature, context="config_signature"),
        )
        object.__setattr__(
            self, "snapshot_id", _ensure_string(self.snapshot_id, context="snapshot_id")
        )


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    pass


def _ensure_string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _ensure_float(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{context} must be a float")
    return float(value)


def _ensure_date(value: object, *, context: str) -> date:
    if not isinstance(value, date):
        raise ValueError(f"{context} must be a date")
    return value


def _ensure_model_label(value: object, *, context: str) -> ModelLabel:
    if not isinstance(value, str) or value not in _MODEL_LABELS:
        raise ValueError(f"{context} must be one of: down, skip, up")
    return cast(ModelLabel, value)


def _ensure_tuple_of(
    value: object,
    item_type: type[_TupleItem],
    *,
    context: str,
) -> tuple[_TupleItem, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{context} must be a tuple")
    normalized = cast(tuple[object, ...], value)
    for item in normalized:
        if not isinstance(item, item_type):
            raise ValueError(f"{context} items must be {item_type.__name__}")
    return cast(tuple[_TupleItem, ...], normalized)
