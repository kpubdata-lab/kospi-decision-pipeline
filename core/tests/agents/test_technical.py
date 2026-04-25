from __future__ import annotations

import math
from pathlib import Path

import pytest

from kospi_decision_pipeline_core.features.leakage_guard import LeakageError
from kospi_decision_pipeline_core.agents import TechnicalAgent
from kospi_decision_pipeline_core.schemas.config import load_agents_config

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "agents.yaml"
EXPECTED_EVIDENCE_NAMES = (
    "kospi_ma5_gap",
    "kospi_close_position",
    "kospi_return_5d",
    "kospi_return_1d",
)


def make_agent() -> TechnicalAgent:
    config = load_agents_config(AGENTS_CONFIG_PATH)
    return TechnicalAgent(
        rule_config=config.agents["technical"],
        weight=config.weights.values["technical"],
    )


@pytest.mark.parametrize(
    ("row", "expected_label", "expected_score"),
    [
        (
            {
                "kospi_return_1d": 0.004,
                "kospi_return_5d": 0.018,
                "kospi_ma5_gap": 0.008,
                "kospi_close_position": 0.72,
            },
            "up",
            0.70,
        ),
        (
            {
                "kospi_return_1d": -0.006,
                "kospi_return_5d": -0.015,
                "kospi_ma5_gap": -0.009,
                "kospi_close_position": 0.28,
            },
            "down",
            -0.70,
        ),
        (
            {
                "kospi_return_1d": 0.007,
                "kospi_return_5d": -0.008,
                "kospi_ma5_gap": 0.001,
                "kospi_close_position": 0.55,
            },
            "skip",
            0.0,
        ),
        (
            {
                "kospi_return_1d": 0.002,
                "kospi_return_5d": 0.006,
                "kospi_ma5_gap": 0.002,
                "kospi_close_position": 0.54,
            },
            "skip",
            0.0,
        ),
    ],
)
def test_technical_agent_matches_spec_truth_table(
    row: dict[str, float],
    expected_label: str,
    expected_score: float,
) -> None:
    vote = make_agent().vote(row)

    assert vote.agent_name == "technical"
    assert vote.rule_version == "technical@1.0.0"
    assert vote.label == expected_label
    assert vote.score == expected_score
    assert vote.weighted_score == vote.score * vote.weight


@pytest.mark.parametrize(
    "row",
    [
        {
            "kospi_return_1d": 0.004,
            "kospi_return_5d": 0.018,
            "kospi_ma5_gap": 0.008,
            "kospi_close_position": 0.72,
        },
        {
            "kospi_return_1d": -0.006,
            "kospi_return_5d": -0.015,
            "kospi_ma5_gap": -0.009,
            "kospi_close_position": 0.28,
        },
        {
            "kospi_return_1d": 0.007,
            "kospi_return_5d": -0.008,
            "kospi_ma5_gap": 0.001,
            "kospi_close_position": 0.55,
        },
        {
            "kospi_return_1d": 0.002,
            "kospi_return_5d": 0.006,
            "kospi_ma5_gap": 0.002,
            "kospi_close_position": 0.54,
        },
    ],
)
def test_technical_agent_emits_all_evidence_items_in_spec_order(
    row: dict[str, float],
) -> None:
    vote = make_agent().vote(row)

    assert tuple(item.name for item in vote.evidence) == EXPECTED_EVIDENCE_NAMES
    assert tuple(item.source for item in vote.evidence) == (
        "computed",
        "computed",
        "computed",
        "computed",
    )
    assert tuple(item.value for item in vote.evidence) == (
        row["kospi_ma5_gap"],
        row["kospi_close_position"],
        row["kospi_return_5d"],
        row["kospi_return_1d"],
    )


@pytest.mark.parametrize("column", EXPECTED_EVIDENCE_NAMES)
def test_technical_agent_nan_in_any_input_falls_back_to_skip(column: str) -> None:
    row: dict[str, float] = {
        "kospi_return_1d": 0.004,
        "kospi_return_5d": 0.018,
        "kospi_ma5_gap": 0.008,
        "kospi_close_position": 0.72,
    }
    row[column] = math.nan

    vote = make_agent().vote(row)

    assert vote.label == "skip"
    assert vote.score == 0.0


@pytest.mark.parametrize("value", [None, math.inf, -math.inf])
def test_technical_agent_non_finite_or_null_inputs_fall_back_to_skip(value: object) -> None:
    row = {
        "kospi_return_1d": 0.004,
        "kospi_return_5d": value,
        "kospi_ma5_gap": 0.008,
        "kospi_close_position": 0.72,
    }

    vote = make_agent().vote(row)

    assert vote.label == "skip"
    assert vote.score == 0.0


def test_technical_agent_rejects_forbidden_target_columns() -> None:
    row = {
        "kospi_return_1d": 0.004,
        "kospi_return_5d": 0.018,
        "kospi_ma5_gap": 0.008,
        "kospi_close_position": 0.72,
        "target_foo": 1.0,
    }

    with pytest.raises(LeakageError, match="forbidden columns"):
        _ = make_agent().vote(row)


def test_technical_agent_rejects_non_whitelisted_columns() -> None:
    row = {
        "kospi_return_1d": 0.004,
        "kospi_return_5d": 0.018,
        "kospi_ma5_gap": 0.008,
        "kospi_close_position": 0.72,
        "other_feature": 1.0,
    }

    with pytest.raises(LeakageError, match="non-whitelisted columns"):
        _ = make_agent().vote(row)
