from __future__ import annotations

from datetime import date

import pytest

from kospi_decision_pipeline_core.schemas.decisions import (
    AgentVote,
    BacktestRow,
    DecisionResult,
    EvidenceItem,
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
        evidence.name = "momentum"


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
        vote.weight = 0.40


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
        decision.votes = ()


def test_backtest_row_construction_and_immutability() -> None:
    row = BacktestRow(
        decision_date=date(2026, 4, 25),
        label="down",
        aggregate_score=-0.41,
        ground_truth="down",
        next_day_return=-0.018,
        hit=True,
    )

    assert row.ground_truth == "down"
    assert row.next_day_return == -0.018
    assert row.hit is True

    with pytest.raises(AttributeError):
        row.hit = False


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: AgentVote(
                agent_name="technical",
                rule_version="technical@v1",
                label="flat",
                score=0.72,
                weight=0.30,
                weighted_score=0.216,
                evidence=(make_evidence_item(),),
            ),
            "label must be one of",
        ),
        (
            lambda: BacktestRow(
                decision_date=date(2026, 4, 25),
                label="skip",
                aggregate_score=0.0,
                ground_truth="skip",
                next_day_return=0.0,
                hit=False,
            ),
            "ground_truth must be one of",
        ),
        (
            lambda: DecisionResult(
                decision_date=date(2026, 4, 25),
                label="flat",
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
def test_runtime_literal_validation(factory: object, match: str) -> None:
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
            evidence=[make_evidence_item()],
        )


def test_decision_result_rejects_non_tuple_votes() -> None:
    with pytest.raises(ValueError, match="votes must be a tuple"):
        _ = DecisionResult(
            decision_date=date(2026, 4, 25),
            label="up",
            aggregate_score=0.42,
            threshold_up=0.25,
            threshold_down=-0.25,
            votes=[make_agent_vote()],
            config_signature="cfg:abc123",
            snapshot_id="snapshot:2026-04-25",
        )
