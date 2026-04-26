from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import cast

import pytest

from kospi_decision_pipeline_core.schemas.decisions import (
    AgentVote,
    DecisionResult,
    EvidenceItem,
    ModelLabel,
)


def make_evidence_item() -> EvidenceItem:
    return EvidenceItem(
        name="volume_zscore",
        value=1.25,
        source="gold.features",
        as_of=date(2026, 4, 24),
    )


def make_agent_vote() -> AgentVote:
    return AgentVote(
        agent_name="technical",
        rule_version="technical@v1",
        label="up",
        score=0.72,
        weight=0.30,
        weighted_score=0.216,
        evidence=(make_evidence_item(),),
    )


def test_evidence_item_construction_and_immutability() -> None:
    evidence = make_evidence_item()

    assert evidence.name == "volume_zscore"
    assert evidence.value == 1.25
    assert evidence.source == "gold.features"
    assert evidence.as_of == date(2026, 4, 24)

    with pytest.raises(AttributeError):
        setattr(evidence, "name", "momentum")


def test_agent_vote_construction_and_immutability() -> None:
    vote = make_agent_vote()

    assert vote.agent_name == "technical"
    assert vote.rule_version == "technical@v1"
    assert vote.label == "up"
    assert vote.score == 0.72
    assert vote.weight == 0.30
    assert vote.weighted_score == 0.216
    assert vote.evidence == (make_evidence_item(),)

    with pytest.raises(AttributeError):
        setattr(vote, "weight", 0.40)


def test_decision_result_construction_and_immutability() -> None:
    decision = DecisionResult(
        decision_date=date(2026, 4, 25),
        label="up",
        aggregate_score=0.42,
        threshold_up=0.25,
        threshold_down=-0.25,
        votes=(make_agent_vote(),),
        config_signature="cfg:abc123",
        snapshot_id="snapshot:2026-04-25",
    )

    assert decision.votes == (make_agent_vote(),)
    assert decision.config_signature == "cfg:abc123"
    assert decision.snapshot_id == "snapshot:2026-04-25"

    with pytest.raises(AttributeError):
        setattr(decision, "votes", ())


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: AgentVote(
                agent_name="technical",
                rule_version="technical@v1",
                label=cast(ModelLabel, cast(object, "flat")),
                score=0.72,
                weight=0.30,
                weighted_score=0.216,
                evidence=(make_evidence_item(),),
            ),
            "label must be one of",
        ),
        (
            lambda: DecisionResult(
                decision_date=date(2026, 4, 25),
                label=cast(ModelLabel, cast(object, "flat")),
                aggregate_score=0.0,
                threshold_up=0.25,
                threshold_down=-0.25,
                votes=(make_agent_vote(),),
                config_signature="cfg:abc123",
                snapshot_id="snapshot:2026-04-25",
            ),
            "label must be one of",
        ),
    ],
)
def test_runtime_literal_validation(factory: Callable[[], object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _ = factory()


def test_agent_vote_rejects_non_tuple_evidence() -> None:
    with pytest.raises(ValueError, match="evidence must be a tuple"):
        _ = AgentVote(
            agent_name="technical",
            rule_version="technical@v1",
            label="up",
            score=0.72,
            weight=0.30,
            weighted_score=0.216,
            evidence=cast(tuple[EvidenceItem, ...], cast(object, [make_evidence_item()])),
        )


def test_decision_result_rejects_non_tuple_votes() -> None:
    with pytest.raises(ValueError, match="votes must be a tuple"):
        _ = DecisionResult(
            decision_date=date(2026, 4, 25),
            label="up",
            aggregate_score=0.42,
            threshold_up=0.25,
            threshold_down=-0.25,
            votes=cast(tuple[AgentVote, ...], cast(object, [make_agent_vote()])),
            config_signature="cfg:abc123",
            snapshot_id="snapshot:2026-04-25",
        )


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: EvidenceItem(
                name=cast(str, cast(object, 1)),
                value=1.25,
                source="gold.features",
                as_of=date(2026, 4, 24),
            ),
            "name must be a string",
        ),
        (
            lambda: EvidenceItem(
                name="volume_zscore",
                value=cast(float, cast(object, True)),
                source="gold.features",
                as_of=date(2026, 4, 24),
            ),
            "value must be a float",
        ),
        (
            lambda: EvidenceItem(
                name="volume_zscore",
                value=1.25,
                source=cast(str, cast(object, 1)),
                as_of=date(2026, 4, 24),
            ),
            "source must be a string",
        ),
        (
            lambda: EvidenceItem(
                name="volume_zscore",
                value=1.25,
                source="gold.features",
                as_of=cast(date, cast(object, "2026-04-24")),
            ),
            "as_of must be a date",
        ),
        (
            lambda: DecisionResult(
                decision_date=date(2026, 4, 25),
                label="up",
                aggregate_score=0.42,
                threshold_up=-0.25,
                threshold_down=-0.25,
                votes=(make_agent_vote(),),
                config_signature="cfg:abc123",
                snapshot_id="snapshot:2026-04-25",
            ),
            "threshold_up must be greater than threshold_down",
        ),
        (
            lambda: AgentVote(
                agent_name="technical",
                rule_version="technical@v1",
                label="up",
                score=0.72,
                weight=0.30,
                weighted_score=0.216,
                evidence=(cast(EvidenceItem, cast(object, "bad")),),
            ),
            "evidence items must be EvidenceItem",
        ),
    ],
)
def test_runtime_type_validation(factory: Callable[[], object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _ = factory()
