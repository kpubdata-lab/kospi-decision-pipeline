from __future__ import annotations

from datetime import date
from math import nan

import pytest

from kospi_decision_pipeline_core.agents.flow import AgentFeatureRow, FlowAgent
from kospi_decision_pipeline_core.features.leakage_guard import LeakageError
from kospi_decision_pipeline_core.schemas.config import AgentRuleConfig


def make_rule_config() -> AgentRuleConfig:
    return AgentRuleConfig(
        rule_version="flow@1.0.0",
        thresholds={
            "foreign_pct_up_min": 0.010,
            "foreign_pct_down_max": -0.010,
            "foreign_pct_neutral_abs_max": 0.003,
        },
    )


def make_agent(*, weight: float = 0.25) -> FlowAgent:
    return FlowAgent(rule_config=make_rule_config(), weight=weight)


def make_row(
    *,
    foreign_5d: float,
    institution_5d: float,
    individual_5d: float,
    foreign_pct: float,
    as_of_date: date = date(2026, 4, 24),
) -> AgentFeatureRow:
    return AgentFeatureRow.from_mapping(
        {
            "as_of_date": as_of_date,
            "foreign_net_buy_krw_5d_sum": foreign_5d,
            "institution_net_buy_krw_5d_sum": institution_5d,
            "individual_net_buy_krw_5d_sum": individual_5d,
            "foreign_net_buy_5d_pct_of_turnover": foreign_pct,
        }
    )


@pytest.mark.parametrize(
    ("row", "expected_label", "expected_score"),
    [
        (
            make_row(
                foreign_5d=1200000000000,
                institution_5d=300000000000,
                individual_5d=-1500000000000,
                foreign_pct=0.012,
            ),
            "up",
            0.80,
        ),
        (
            make_row(
                foreign_5d=-1000000000000,
                institution_5d=-200000000000,
                individual_5d=1200000000000,
                foreign_pct=-0.013,
            ),
            "down",
            -0.80,
        ),
        (
            make_row(
                foreign_5d=500000000000,
                institution_5d=-100000000000,
                individual_5d=-400000000000,
                foreign_pct=0.006,
            ),
            "skip",
            0.0,
        ),
        (
            make_row(
                foreign_5d=400000000000,
                institution_5d=100000000000,
                individual_5d=-500000000000,
                foreign_pct=0.005,
            ),
            "skip",
            0.0,
        ),
    ],
)
def test_flow_agent_truth_table(
    row: AgentFeatureRow,
    expected_label: str,
    expected_score: float,
) -> None:
    vote = make_agent().vote(row)

    assert vote.agent_name == "flow"
    assert vote.rule_version == "flow@1.0.0"
    assert vote.label == expected_label
    assert vote.score == pytest.approx(expected_score)


def test_flow_agent_preserves_specified_evidence_order_sources_and_weighted_score() -> None:
    row = make_row(
        foreign_5d=1200000000000,
        institution_5d=300000000000,
        individual_5d=-1500000000000,
        foreign_pct=0.012,
        as_of_date=date(2026, 4, 25),
    )

    vote = make_agent(weight=0.25).vote(row)

    assert vote.weight == pytest.approx(0.25)
    assert vote.weighted_score == pytest.approx(0.20)
    assert tuple((item.name, item.source, item.value, item.as_of) for item in vote.evidence) == (
        (
            "foreign_net_buy_krw_5d_sum",
            "KRX",
            1200000000000,
            date(2026, 4, 25),
        ),
        (
            "institution_net_buy_krw_5d_sum",
            "KRX",
            300000000000,
            date(2026, 4, 25),
        ),
        (
            "individual_net_buy_krw_5d_sum",
            "KRX",
            -1500000000000,
            date(2026, 4, 25),
        ),
        (
            "foreign_net_buy_5d_pct_of_turnover",
            "computed",
            0.012,
            date(2026, 4, 25),
        ),
    )


@pytest.mark.parametrize(
    ("foreign_5d", "institution_5d", "individual_5d", "foreign_pct"),
    [
        (nan, 300000000000, -1500000000000, 0.012),
        (1200000000000, nan, -1500000000000, 0.012),
        (1200000000000, 300000000000, nan, 0.012),
        (1200000000000, 300000000000, -1500000000000, nan),
    ],
)
def test_flow_agent_treats_any_nan_predicate_input_as_not_matched(
    foreign_5d: float,
    institution_5d: float,
    individual_5d: float,
    foreign_pct: float,
) -> None:
    vote = make_agent().vote(
        make_row(
            foreign_5d=foreign_5d,
            institution_5d=institution_5d,
            individual_5d=individual_5d,
            foreign_pct=foreign_pct,
        )
    )

    assert vote.label == "skip"
    assert vote.score == pytest.approx(0.0)
    assert vote.weighted_score == pytest.approx(0.0)


def test_agent_feature_row_rejects_forbidden_target_columns() -> None:
    with pytest.raises(LeakageError, match="forbidden columns"):
        _ = AgentFeatureRow.from_mapping(
            {
                "as_of_date": date(2026, 4, 24),
                "foreign_net_buy_krw_5d_sum": 1.0,
                "institution_net_buy_krw_5d_sum": 0.0,
                "individual_net_buy_krw_5d_sum": -1.0,
                "foreign_net_buy_5d_pct_of_turnover": 0.02,
                "target_direction_label": "up",
            }
        )


def test_agent_feature_row_rejects_non_whitelisted_columns() -> None:
    with pytest.raises(LeakageError, match="non-whitelisted columns"):
        _ = AgentFeatureRow.from_mapping(
            {
                "as_of_date": date(2026, 4, 24),
                "foreign_net_buy_krw_5d_sum": 1.0,
                "institution_net_buy_krw_5d_sum": 0.0,
                "individual_net_buy_krw_5d_sum": -1.0,
                "foreign_net_buy_5d_pct_of_turnover": 0.02,
                "institution_net_buy_5d_pct_of_turnover": 0.01,
            }
        )


def test_flow_agent_exposes_spec_whitelist_verbatim() -> None:
    assert FlowAgent.INPUT_WHITELIST == (
        "foreign_net_buy_krw_5d_sum",
        "institution_net_buy_krw_5d_sum",
        "individual_net_buy_krw_5d_sum",
        "foreign_net_buy_5d_pct_of_turnover",
    )
