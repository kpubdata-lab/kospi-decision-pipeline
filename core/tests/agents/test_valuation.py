from __future__ import annotations

from math import nan
from typing import TYPE_CHECKING

import pytest

from kospi_decision_pipeline_core.schemas import AgentRuleConfig

if TYPE_CHECKING:
    from kospi_decision_pipeline_core.agents.valuation import ValuationAgent


def _make_rule_config() -> AgentRuleConfig:
    return AgentRuleConfig(
        rule_version="valuation@1.0.0",
        thresholds={
            "per_percentile_up_max": 0.30,
            "pbr_percentile_up_max": 0.30,
            "per_percentile_down_min": 0.70,
            "pbr_percentile_down_min": 0.70,
            "fair_value_center": 0.50,
            "fair_value_half_band": 0.10,
        },
    )


def _make_agent(weight: float = 0.10) -> ValuationAgent:
    from kospi_decision_pipeline_core.agents.valuation import ValuationAgent

    return ValuationAgent(rule_config=_make_rule_config(), weight=weight)


@pytest.mark.parametrize(
    ("row", "expected_label", "expected_score"),
    [
        pytest.param(
            {
                "kospi_per": 9.8,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": 0.18,
                "kospi_pbr_percentile_252d": 0.22,
            },
            "up",
            0.55,
            id="v1-cheap-market",
        ),
        pytest.param(
            {
                "kospi_per": 13.8,
                "kospi_pbr": 1.18,
                "kospi_per_percentile_252d": 0.82,
                "kospi_pbr_percentile_252d": 0.76,
            },
            "down",
            -0.55,
            id="v2-expensive-market",
        ),
        pytest.param(
            {
                "kospi_per": 11.5,
                "kospi_pbr": 0.98,
                "kospi_per_percentile_252d": 0.54,
                "kospi_pbr_percentile_252d": 0.47,
            },
            "skip",
            0.0,
            id="v3-fair-value-abstain",
        ),
        pytest.param(
            {
                "kospi_per": 10.9,
                "kospi_pbr": 1.05,
                "kospi_per_percentile_252d": 0.20,
                "kospi_pbr_percentile_252d": 0.65,
            },
            "skip",
            0.0,
            id="v4-fallback",
        ),
    ],
)
def test_valuation_agent_truth_table(
    row: dict[str, float], expected_label: str, expected_score: float
) -> None:
    vote = _make_agent().vote(row)

    assert vote.agent_name == "valuation"
    assert vote.rule_version == "valuation@1.0.0"
    assert vote.label == expected_label
    assert vote.score == expected_score


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            {
                "kospi_per": 9.8,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": nan,
                "kospi_pbr_percentile_252d": 0.22,
            },
            id="nan-percentile-falls-through",
        ),
        pytest.param(
            {
                "kospi_per": -9.8,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": 0.18,
                "kospi_pbr_percentile_252d": 0.22,
            },
            id="negative-per-falls-through",
        ),
        pytest.param(
            {
                "kospi_per": 9.8,
                "kospi_pbr": -0.86,
                "kospi_per_percentile_252d": 0.18,
                "kospi_pbr_percentile_252d": 0.22,
            },
            id="negative-pbr-falls-through",
        ),
    ],
)
def test_valuation_agent_non_matching_inputs_fall_through_to_skip(row: dict[str, float]) -> None:
    vote = _make_agent().vote(row)

    assert vote.label == "skip"
    assert vote.score == 0.0
    assert vote.weighted_score == 0.0


def test_valuation_agent_emits_evidence_in_spec_order_with_weighted_score() -> None:
    vote = _make_agent(weight=0.10).vote(
        {
            "kospi_per": 9.8,
            "kospi_pbr": 0.86,
            "kospi_per_percentile_252d": 0.18,
            "kospi_pbr_percentile_252d": 0.22,
        }
    )

    assert vote.weight == 0.10
    assert vote.weighted_score == pytest.approx(0.055)
    assert tuple((item.name, item.source, item.value) for item in vote.evidence) == (
        ("kospi_per", "KRX", 9.8),
        ("kospi_pbr", "KRX", 0.86),
        ("kospi_per_percentile_252d", "computed", 0.18),
        ("kospi_pbr_percentile_252d", "computed", 0.22),
    )


def test_valuation_agent_rejects_non_whitelisted_inputs() -> None:
    with pytest.raises(ValueError, match="non-whitelisted inputs"):
        _ = _make_agent().vote(
            {
                "kospi_per": 9.8,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": 0.18,
                "kospi_pbr_percentile_252d": 0.22,
                "future_hint": 1.0,
            }
        )


def test_valuation_agent_rejects_missing_required_inputs() -> None:
    with pytest.raises(ValueError, match="missing required inputs"):
        _ = _make_agent().vote(
            {
                "kospi_per": 9.8,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": 0.18,
            }
        )


def test_valuation_agent_rejects_non_numeric_inputs() -> None:
    with pytest.raises(ValueError, match="kospi_per must be numeric"):
        _ = _make_agent().vote(
            {
                "kospi_per": True,
                "kospi_pbr": 0.86,
                "kospi_per_percentile_252d": 0.18,
                "kospi_pbr_percentile_252d": 0.22,
            }
        )


def test_valuation_agent_constants_match_spec() -> None:
    from kospi_decision_pipeline_core.agents import ValuationAgent

    assert ValuationAgent.AGENT_NAME == "valuation"
    assert ValuationAgent.INPUT_WHITELIST == (
        "kospi_per",
        "kospi_pbr",
        "kospi_per_percentile_252d",
        "kospi_pbr_percentile_252d",
    )
