from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from math import nan

import pytest

from kospi_decision_pipeline_core.features.leakage_guard import LeakageError
from kospi_decision_pipeline_core.schemas import AgentRuleConfig

from kospi_decision_pipeline_core.agents import DomesticMacroAgent


def make_rule_config() -> AgentRuleConfig:
    return AgentRuleConfig(
        rule_version="domestic_macro@1.0.0",
        thresholds={
            "bok_rate_change_up_max": 0.00,
            "usdkrw_return_5d_up_max": 0.010,
            "bond_yield_change_30d_up_max": 0.05,
            "bok_rate_change_down_min": 0.25,
            "usdkrw_return_5d_down_min": 0.020,
            "bond_yield_change_30d_down_min": 0.10,
            "usdkrw_return_5d_mixed_pos_min": 0.015,
            "usdkrw_return_5d_mixed_neg_max": -0.015,
            "bond_yield_change_30d_mixed_pos_min": 0.05,
            "bond_yield_change_30d_mixed_neg_max": 0.00,
        },
    )


def make_agent(weight: float = 0.20) -> DomesticMacroAgent:
    return DomesticMacroAgent(rule_config=make_rule_config(), weight=weight)


def make_row(
    *,
    bok_change: float,
    usdkrw_5d: float,
    bond_change: float,
) -> Mapping[str, float]:
    return {
        "bok_base_rate_change_30d": bok_change,
        "usd_krw_return_5d": usdkrw_5d,
        "kr_bond_yield_change_30d": bond_change,
    }


@pytest.mark.parametrize(
    ("bok_change", "usdkrw_5d", "bond_change", "label", "score"),
    [
        pytest.param(0.00, -0.004, -0.02, "up", 0.60, id="M1-supportive"),
        pytest.param(0.25, 0.005, 0.01, "down", -0.70, id="M2-risk-off"),
        pytest.param(0.00, 0.018, -0.03, "skip", 0.0, id="M3-conflicting-signals"),
        pytest.param(0.00, 0.008, 0.07, "skip", 0.0, id="M4-fallback"),
    ],
)
def test_domestic_macro_truth_table(
    bok_change: float,
    usdkrw_5d: float,
    bond_change: float,
    label: str,
    score: float,
) -> None:
    agent = make_agent()

    vote = agent.vote(
        make_row(
            bok_change=bok_change,
            usdkrw_5d=usdkrw_5d,
            bond_change=bond_change,
        )
    )

    assert vote.agent_name == "domestic_macro"
    assert vote.rule_version == "domestic_macro@1.0.0"
    assert vote.label == label
    assert vote.score == score


@pytest.mark.parametrize(
    ("row",),
    [
        pytest.param(
            make_row(bok_change=nan, usdkrw_5d=-0.004, bond_change=-0.02),
            id="supportive-branch-nan",
        ),
        pytest.param(
            make_row(bok_change=nan, usdkrw_5d=0.025, bond_change=0.12),
            id="risk-off-left-side-nan",
        ),
        pytest.param(
            make_row(bok_change=0.00, usdkrw_5d=0.018, bond_change=nan),
            id="conflicting-branch-nan",
        ),
    ],
)
def test_domestic_macro_nan_inputs_make_referenced_branch_not_match(
    row: Mapping[str, float],
) -> None:
    vote = make_agent().vote(row)

    assert vote.label == "skip"
    assert vote.score == 0.0


def test_domestic_macro_emits_ordered_computed_evidence_and_weighted_score() -> None:
    vote = make_agent(weight=0.20).vote(
        make_row(
            bok_change=0.00,
            usdkrw_5d=-0.004,
            bond_change=-0.02,
        )
    )

    assert vote.weight == 0.20
    assert vote.weighted_score == 0.12
    assert tuple(item.name for item in vote.evidence) == (
        "bok_base_rate_change_30d",
        "usd_krw_return_5d",
        "kr_bond_yield_change_30d",
    )
    assert tuple(item.value for item in vote.evidence) == (0.00, -0.004, -0.02)
    assert tuple(item.source for item in vote.evidence) == ("computed", "computed", "computed")
    assert tuple(item.as_of for item in vote.evidence) == (date.min, date.min, date.min)


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(
            {
                **make_row(bok_change=0.00, usdkrw_5d=-0.004, bond_change=-0.02),
                "future_hint": 1.0,
            },
            id="forbidden-prefix",
        ),
        pytest.param(
            {
                **make_row(bok_change=0.00, usdkrw_5d=-0.004, bond_change=-0.02),
                "surprise_feature": 1.0,
            },
            id="non-whitelisted-column",
        ),
    ],
)
def test_domestic_macro_rejects_leakage_and_non_whitelisted_inputs(
    row: Mapping[str, float],
) -> None:
    with pytest.raises(LeakageError):
        _ = make_agent().vote(row)


def test_domestic_macro_rejects_non_finite_weight() -> None:
    with pytest.raises(ValueError, match="weight must be finite"):
        _ = make_agent(weight=nan)


def test_domestic_macro_requires_all_features() -> None:
    with pytest.raises(ValueError, match="missing required feature: usd_krw_return_5d"):
        _ = make_agent().vote(
            {
                "bok_base_rate_change_30d": 0.00,
                "kr_bond_yield_change_30d": -0.02,
            }
        )


def test_domestic_macro_rejects_non_numeric_feature_values() -> None:
    with pytest.raises(ValueError, match="usd_krw_return_5d must be numeric"):
        _ = make_agent().vote(
            {
                "bok_base_rate_change_30d": 0.00,
                "usd_krw_return_5d": "0.001",
                "kr_bond_yield_change_30d": -0.02,
            }
        )


def test_domestic_macro_requires_all_thresholds() -> None:
    thresholds = deepcopy(dict(make_rule_config().thresholds))
    del thresholds["usdkrw_return_5d_up_max"]

    agent = DomesticMacroAgent(
        rule_config=AgentRuleConfig(rule_version="domestic_macro@1.0.0", thresholds=thresholds),
        weight=0.20,
    )

    with pytest.raises(ValueError, match="missing threshold: usdkrw_return_5d_up_max"):
        _ = agent.vote(make_row(bok_change=0.00, usdkrw_5d=-0.004, bond_change=-0.02))
