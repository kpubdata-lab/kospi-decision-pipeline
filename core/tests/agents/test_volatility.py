from __future__ import annotations

from datetime import date
from math import isnan

import pytest

from kospi_decision_pipeline_core.features.leakage_guard import LeakageError
from kospi_decision_pipeline_core.schemas import AgentRuleConfig

from kospi_decision_pipeline_core.agents.volatility import AgentFeatureRow, VolatilityAgent


def make_agent() -> VolatilityAgent:
    return VolatilityAgent(
        rule_config=AgentRuleConfig(
            rule_version="volatility@1.0.0",
            thresholds={
                "realized_vol_20d_up_max": 0.18,
                "realized_vol_pct_up_max": 0.30,
                "atr_14d_up_max": 35.0,
                "realized_vol_pct_down_min": 0.80,
                "realized_vol_20d_down_min": 0.25,
                "atr_14d_down_min": 45.0,
                "realized_vol_pct_mid_low": 0.30,
                "realized_vol_pct_mid_high": 0.80,
            },
        ),
        weight=0.15,
    )


def make_row(
    *,
    rv20d: float,
    rv_pct: float,
    atr14: float,
    as_of: date = date(2026, 4, 25),
) -> AgentFeatureRow:
    return AgentFeatureRow(
        as_of=as_of,
        values={
            "kospi_realized_vol_20d": rv20d,
            "kospi_realized_vol_20d_percentile_252d": rv_pct,
            "kospi_atr_14d": atr14,
        },
    )


@pytest.mark.parametrize(
    ("row", "label", "score"),
    [
        (make_row(rv20d=0.15, rv_pct=0.22, atr14=28.0), "up", 0.40),
        (make_row(rv20d=0.29, rv_pct=0.88, atr14=47.0), "down", -0.65),
        (make_row(rv20d=0.21, rv_pct=0.55, atr14=34.0), "skip", 0.0),
        (make_row(rv20d=0.20, rv_pct=0.85, atr14=30.0), "skip", 0.0),
    ],
)
def test_volatility_agent_truth_table(
    row: AgentFeatureRow,
    label: str,
    score: float,
) -> None:
    vote = make_agent().vote(row)

    assert vote.agent_name == "volatility"
    assert vote.rule_version == "volatility@1.0.0"
    assert vote.label == label
    assert vote.score == score


def test_volatility_agent_uses_inclusive_and_exclusive_threshold_edges() -> None:
    agent = make_agent()

    calm_vote = agent.vote(make_row(rv20d=0.18, rv_pct=0.30, atr14=35.0))
    stress_vote = agent.vote(make_row(rv20d=0.25, rv_pct=0.80, atr14=44.0))
    low_boundary_fallback = agent.vote(make_row(rv20d=0.19, rv_pct=0.30, atr14=36.0))
    high_boundary_fallback = agent.vote(make_row(rv20d=0.24, rv_pct=0.80, atr14=44.0))

    assert calm_vote.label == "up"
    assert calm_vote.score == 0.40
    assert stress_vote.label == "down"
    assert stress_vote.score == -0.65
    assert low_boundary_fallback.label == "skip"
    assert low_boundary_fallback.score == 0.0
    assert high_boundary_fallback.label == "skip"
    assert high_boundary_fallback.score == 0.0


def test_volatility_agent_treats_nan_inputs_as_not_matched() -> None:
    vote = make_agent().vote(make_row(rv20d=0.15, rv_pct=float("nan"), atr14=28.0))

    assert vote.label == "skip"
    assert vote.score == 0.0
    assert isnan(vote.evidence[1].value)


def test_volatility_agent_emits_evidence_in_spec_order_with_sources_and_weighting() -> None:
    vote = make_agent().vote(make_row(rv20d=0.15, rv_pct=0.22, atr14=28.0))

    assert vote.weight == 0.15
    assert vote.weighted_score == 0.06
    assert tuple(item.name for item in vote.evidence) == (
        "kospi_realized_vol_20d",
        "kospi_realized_vol_20d_percentile_252d",
        "kospi_atr_14d",
    )
    assert tuple(item.source for item in vote.evidence) == ("computed", "computed", "computed")
    assert tuple(item.value for item in vote.evidence) == (0.15, 0.22, 28.0)
    assert tuple(item.as_of for item in vote.evidence) == (
        date(2026, 4, 25),
        date(2026, 4, 25),
        date(2026, 4, 25),
    )


def test_volatility_agent_rejects_non_whitelisted_inputs() -> None:
    row = AgentFeatureRow(
        as_of=date(2026, 4, 25),
        values={
            "kospi_realized_vol_20d": 0.15,
            "kospi_realized_vol_20d_percentile_252d": 0.22,
            "kospi_atr_14d": 28.0,
            "target_direction_label": "up",
        },
    )

    with pytest.raises(LeakageError, match="forbidden columns"):
        _ = make_agent().vote(row)


def test_volatility_agent_rejects_unknown_extra_inputs() -> None:
    row = AgentFeatureRow(
        as_of=date(2026, 4, 25),
        values={
            "kospi_realized_vol_20d": 0.15,
            "kospi_realized_vol_20d_percentile_252d": 0.22,
            "kospi_atr_14d": 28.0,
            "surprise_feature": 1.0,
        },
    )

    with pytest.raises(LeakageError, match="non-whitelisted columns"):
        _ = make_agent().vote(row)


def test_volatility_agent_allows_missing_values_as_nan_fallback() -> None:
    vote = make_agent().vote(
        AgentFeatureRow(
            as_of=date(2026, 4, 25),
            values={
                "kospi_realized_vol_20d": 0.15,
                "kospi_atr_14d": 28.0,
            },
        )
    )

    assert vote.label == "skip"
    assert vote.score == 0.0
    assert isnan(vote.evidence[1].value)


def test_volatility_agent_rejects_unsupported_feature_values() -> None:
    row = AgentFeatureRow(
        as_of=date(2026, 4, 25),
        values={
            "kospi_realized_vol_20d": 0.15,
            "kospi_realized_vol_20d_percentile_252d": "0.22",
            "kospi_atr_14d": 28.0,
        },
    )

    with pytest.raises(LeakageError, match="unsupported feature value"):
        _ = make_agent().vote(row)


def test_volatility_agent_validates_rule_version_and_weight() -> None:
    with pytest.raises(ValueError, match="rule_version must equal volatility@1.0.0"):
        _ = VolatilityAgent(
            rule_config=AgentRuleConfig(
                rule_version="volatility@0.9.0",
                thresholds={
                    "realized_vol_20d_up_max": 0.18,
                    "realized_vol_pct_up_max": 0.30,
                    "atr_14d_up_max": 35.0,
                    "realized_vol_pct_down_min": 0.80,
                    "realized_vol_20d_down_min": 0.25,
                    "atr_14d_down_min": 45.0,
                    "realized_vol_pct_mid_low": 0.30,
                    "realized_vol_pct_mid_high": 0.80,
                },
            ),
            weight=0.15,
        )

    with pytest.raises(ValueError, match="weight must be a float"):
        _ = VolatilityAgent(rule_config=make_agent().rule_config, weight=True)
