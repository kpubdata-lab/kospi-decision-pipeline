from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import pytest

from kospi_decision_pipeline_core.agents import DecisionAgent, compute_config_signature
from kospi_decision_pipeline_core.schemas.decisions import AgentVote, EvidenceItem


DECISION_DATE = date(2026, 4, 25)
CONFIG_SIGNATURE = "cfg:decision"
SNAPSHOT_ID = "snapshot:2026-04-25"


def make_vote(
    agent_name: str,
    label: Literal["up", "down", "skip"],
    weight: float,
    *,
    score: float | None = None,
) -> AgentVote:
    resolved_score = score
    if resolved_score is None:
        if label == "up":
            resolved_score = 0.70
        elif label == "down":
            resolved_score = -0.70
        else:
            resolved_score = 0.0

    return AgentVote(
        agent_name=agent_name,
        rule_version=f"{agent_name}@1.0.0",
        label=label,
        score=resolved_score,
        weight=weight,
        weighted_score=resolved_score * weight,
        evidence=(
            EvidenceItem(
                name=f"{agent_name}_signal",
                value=resolved_score,
                source="test",
                as_of=DECISION_DATE,
            ),
        ),
    )


def make_agent(*, threshold_up: float = 0.25, threshold_down: float = -0.25) -> DecisionAgent:
    return DecisionAgent(
        threshold_up=threshold_up,
        threshold_down=threshold_down,
        config_signature=CONFIG_SIGNATURE,
    )


@pytest.mark.parametrize(
    ("votes", "expected_score", "expected_label"),
    [
        (
            (
                make_vote("technical", "up", 0.30),
                make_vote("domestic_macro", "up", 0.20),
                make_vote("flow", "up", 0.25),
                make_vote("valuation", "up", 0.10),
                make_vote("volatility", "up", 0.15),
            ),
            1.0,
            "up",
        ),
        (
            (
                make_vote("technical", "down", 0.30),
                make_vote("domestic_macro", "down", 0.20),
                make_vote("flow", "down", 0.25),
                make_vote("valuation", "down", 0.10),
                make_vote("volatility", "down", 0.15),
            ),
            -1.0,
            "down",
        ),
        (
            (
                make_vote("technical", "skip", 0.30),
                make_vote("domestic_macro", "skip", 0.20),
                make_vote("flow", "skip", 0.25),
                make_vote("valuation", "skip", 0.10),
                make_vote("volatility", "skip", 0.15),
            ),
            0.0,
            "skip",
        ),
        (
            (make_vote("alpha", "up", 0.25), make_vote("beta", "skip", 0.75)),
            0.25,
            "skip",
        ),
        (
            (make_vote("alpha", "down", 0.25), make_vote("beta", "skip", 0.75)),
            -0.25,
            "skip",
        ),
        (
            (make_vote("alpha", "up", 0.26), make_vote("beta", "skip", 0.74)),
            0.26,
            "up",
        ),
        (
            (make_vote("alpha", "down", 0.26), make_vote("beta", "skip", 0.74)),
            -0.26,
            "down",
        ),
        (
            (
                make_vote("technical", "up", 0.30, score=0.70),
                make_vote("flow", "up", 0.25, score=0.80),
                make_vote("domestic_macro", "skip", 0.20),
                make_vote("valuation", "skip", 0.10),
                make_vote("volatility", "skip", 0.15),
            ),
            0.55,
            "up",
        ),
        (
            (
                make_vote("technical", "up", 0.30, score=0.70),
                make_vote("flow", "down", 0.25, score=-0.80),
                make_vote("domestic_macro", "skip", 0.20),
                make_vote("valuation", "skip", 0.10),
                make_vote("volatility", "skip", 0.15),
            ),
            0.05,
            "skip",
        ),
    ],
)
def test_decision_agent_aggregation_truth_table(
    votes: tuple[AgentVote, ...],
    expected_score: float,
    expected_label: str,
) -> None:
    result = make_agent().decide(
        decision_date=DECISION_DATE,
        votes=votes,
        snapshot_id=SNAPSHOT_ID,
    )

    assert abs(result.aggregate_score - expected_score) < 1e-12
    assert result.label == expected_label


def test_decision_agent_sorts_votes_and_populates_result_fields() -> None:
    votes = (
        make_vote("volatility", "skip", 0.15),
        make_vote("technical", "up", 0.30),
        make_vote("flow", "up", 0.25),
        make_vote("valuation", "skip", 0.10),
        make_vote("domestic_macro", "skip", 0.20),
    )

    result = make_agent().decide(
        decision_date=DECISION_DATE,
        votes=votes,
        snapshot_id=SNAPSHOT_ID,
    )

    assert tuple(vote.agent_name for vote in result.votes) == (
        "domestic_macro",
        "flow",
        "technical",
        "valuation",
        "volatility",
    )
    assert result.decision_date == DECISION_DATE
    assert result.threshold_up == 0.25
    assert result.threshold_down == -0.25
    assert result.config_signature == CONFIG_SIGNATURE
    assert result.snapshot_id == SNAPSHOT_ID


def test_decision_agent_rejects_empty_votes() -> None:
    with pytest.raises(ValueError, match="at least one vote required"):
        _ = make_agent().decide(
            decision_date=DECISION_DATE,
            votes=(),
            snapshot_id=SNAPSHOT_ID,
        )


def test_decision_agent_rejects_duplicate_agent_names() -> None:
    with pytest.raises(ValueError, match="duplicate agent_name: technical"):
        _ = make_agent().decide(
            decision_date=DECISION_DATE,
            votes=(
                make_vote("technical", "up", 0.30),
                make_vote("technical", "down", 0.70),
            ),
            snapshot_id=SNAPSHOT_ID,
        )


def test_decision_agent_is_deterministic_across_input_order() -> None:
    first_votes = (
        make_vote("volatility", "skip", 0.15),
        make_vote("technical", "up", 0.30),
        make_vote("flow", "up", 0.25),
        make_vote("valuation", "skip", 0.10),
        make_vote("domestic_macro", "skip", 0.20),
    )
    second_votes = (
        make_vote("domestic_macro", "skip", 0.20),
        make_vote("valuation", "skip", 0.10),
        make_vote("flow", "up", 0.25),
        make_vote("technical", "up", 0.30),
        make_vote("volatility", "skip", 0.15),
    )

    first = make_agent().decide(
        decision_date=DECISION_DATE,
        votes=first_votes,
        snapshot_id=SNAPSHOT_ID,
    )
    second = make_agent().decide(
        decision_date=DECISION_DATE,
        votes=second_votes,
        snapshot_id=SNAPSHOT_ID,
    )

    assert first == second


def test_compute_config_signature_is_stable_for_equal_yaml(tmp_path: Path) -> None:
    left = tmp_path / "left.yaml"
    right = tmp_path / "right.yaml"
    _ = left.write_text(
        "weights:\n  technical: 0.3\nthresholds:\n  up: 0.25\n  down: -0.25\n", encoding="utf-8"
    )
    _ = right.write_text(
        "thresholds:\n  down: -0.25\n  up: 0.25\nweights:\n  technical: 0.3\n",
        encoding="utf-8",
    )

    assert compute_config_signature(left) == compute_config_signature(right)


def test_compute_config_signature_changes_when_yaml_changes(tmp_path: Path) -> None:
    left = tmp_path / "left.yaml"
    right = tmp_path / "right.yaml"
    _ = left.write_text("thresholds:\n  up: 0.25\n  down: -0.25\n", encoding="utf-8")
    _ = right.write_text("thresholds:\n  up: 0.26\n  down: -0.25\n", encoding="utf-8")

    assert compute_config_signature(left) != compute_config_signature(right)


def test_compute_config_signature_ignores_whitespace_only_differences(tmp_path: Path) -> None:
    left = tmp_path / "left.yaml"
    right = tmp_path / "right.yaml"
    _ = left.write_text("weights:\n  technical: 0.3\n", encoding="utf-8")
    _ = right.write_text("weights:\n\n  technical: 0.3\n\n", encoding="utf-8")

    assert compute_config_signature(left) == compute_config_signature(right)
