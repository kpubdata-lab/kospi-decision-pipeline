from __future__ import annotations

from datetime import date

from abdp.agents import AgentContext
from abdp.core.types import Seed
from abdp.simulation import SimulationState, SnapshotRef
import pytest

from kospi_decision_pipeline_core.agents import (
    DecisionAgent,
    DomesticMacroAgent,
    FlowAgent,
    TechnicalAgent,
    ValuationAgent,
    VolatilityAgent,
)
from kospi_decision_pipeline_core.runtime.adapters import (
    DecisionAgentAdapter,
    DomesticMacroAgentAdapter,
    FlowAgentAdapter,
    TechnicalAgentAdapter,
    ValuationAgentAdapter,
    VolatilityAgentAdapter,
)
from kospi_decision_pipeline_core.runtime import adapters as adapter_module
from kospi_decision_pipeline_core.runtime.models import (
    KospiActionProposal,
    KospiDecisionParticipant,
    KospiDecisionSegment,
    ScenarioPhase,
)
from kospi_decision_pipeline_core.schemas import AgentRuleConfig, AgentVote, ThresholdsConfig
from uuid import UUID


def _rule_config(rule_version: str, **thresholds: float) -> AgentRuleConfig:
    return AgentRuleConfig(rule_version=rule_version, thresholds=thresholds)


def _features_row() -> dict[str, object]:
    return {
        "as_of_date": date(2025, 2, 13),
        "kospi_return_1d": 0.01,
        "kospi_return_5d": 0.02,
        "kospi_ma5_gap": 0.01,
        "kospi_close_position": 0.75,
        "bok_base_rate_change_30d": 0.0,
        "usd_krw_return_5d": 0.0,
        "kr_bond_yield_change_30d": 0.0,
        "foreign_net_buy_krw_5d_sum": 10.0,
        "institution_net_buy_krw_5d_sum": 5.0,
        "individual_net_buy_krw_5d_sum": -15.0,
        "foreign_net_buy_5d_pct_of_turnover": 0.02,
        "kospi_per": 10.0,
        "kospi_pbr": 1.0,
        "kospi_per_percentile_252d": 0.2,
        "kospi_pbr_percentile_252d": 0.2,
        "kospi_realized_vol_20d": 0.15,
        "kospi_realized_vol_20d_percentile_252d": 0.2,
        "kospi_atr_14d": 12.0,
    }


def _segment(
    *,
    phase: ScenarioPhase,
    votes: tuple[AgentVote, ...] = (),
) -> KospiDecisionSegment:
    return KospiDecisionSegment(
        segment_id="segment-kospi",
        participant_ids=("market-kospi",),
        phase=phase,
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row=_features_row(),
        votes=votes,
        decision_result=None,
    )


def _state(
    segment: KospiDecisionSegment,
) -> SimulationState[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]:
    return SimulationState(
        step_index=0,
        seed=Seed(7),
        snapshot_ref=SnapshotRef(
            snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
            tier="gold",
            storage_key="data/gold/features.parquet",
        ),
        segments=(segment,),
        participants=(KospiDecisionParticipant(participant_id="market-kospi"),),
        pending_actions=(),
    )


def _context(
    segment: KospiDecisionSegment,
    *,
    step_index: int,
) -> AgentContext[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal]:
    return AgentContext(
        scenario_key="kospi.next_day",
        agent_id="test-agent",
        step_index=step_index,
        seed=Seed(7),
        state=_state(segment),
    )


def test_rule_adapters_emit_votes_only_during_vote_phase() -> None:
    segment = _segment(phase="vote")
    adapters = (
        TechnicalAgentAdapter(
            agent=TechnicalAgent(
                rule_config=_rule_config(
                    "technical@1.0.0",
                    ma5_gap_up_min=0.005,
                    close_position_up_min=0.60,
                    return_5d_up_min=0.010,
                    ma5_gap_down_max=-0.005,
                    close_position_down_max=0.40,
                    return_5d_down_max=-0.010,
                ),
                weight=0.30,
            )
        ),
        DomesticMacroAgentAdapter(
            agent=DomesticMacroAgent(
                rule_config=_rule_config(
                    "domestic_macro@1.0.0",
                    bok_rate_change_up_max=0.00,
                    usdkrw_return_5d_up_max=0.010,
                    bond_yield_change_30d_up_max=0.05,
                    bok_rate_change_down_min=0.25,
                    usdkrw_return_5d_down_min=0.020,
                    bond_yield_change_30d_down_min=0.10,
                    usdkrw_return_5d_mixed_pos_min=0.015,
                    usdkrw_return_5d_mixed_neg_max=-0.015,
                    bond_yield_change_30d_mixed_pos_min=0.05,
                    bond_yield_change_30d_mixed_neg_max=0.00,
                ),
                weight=0.20,
            )
        ),
        FlowAgentAdapter(
            agent=FlowAgent(
                rule_config=_rule_config(
                    "flow@1.0.0",
                    foreign_pct_up_min=0.010,
                    foreign_pct_down_max=-0.010,
                    foreign_pct_neutral_abs_max=0.003,
                ),
                weight=0.25,
            )
        ),
        ValuationAgentAdapter(
            agent=ValuationAgent(
                rule_config=_rule_config(
                    "valuation@1.0.0",
                    per_percentile_up_max=0.30,
                    pbr_percentile_up_max=0.30,
                    per_percentile_down_min=0.70,
                    pbr_percentile_down_min=0.70,
                    fair_value_center=0.50,
                    fair_value_half_band=0.10,
                ),
                weight=0.10,
            )
        ),
        VolatilityAgentAdapter(
            agent=VolatilityAgent(
                rule_config=_rule_config(
                    "volatility@1.0.0",
                    realized_vol_20d_up_max=0.18,
                    realized_vol_pct_up_max=0.30,
                    atr_14d_up_max=35.0,
                    realized_vol_pct_down_min=0.80,
                    realized_vol_20d_down_min=0.25,
                    atr_14d_down_min=45.0,
                    realized_vol_pct_mid_low=0.30,
                    realized_vol_pct_mid_high=0.80,
                ),
                weight=0.15,
            )
        ),
    )

    for adapter in adapters:
        decision = adapter.decide(_context(segment, step_index=0))
        assert decision.agent_id == adapter.agent_id
        assert len(decision.proposals) == 1
        assert decision.proposals[0].actor_id == adapter.agent_id
        assert decision.proposals[0].payload["vote"]


def test_rule_adapters_emit_empty_proposals_outside_vote_phase() -> None:
    adapter = TechnicalAgentAdapter(
        agent=TechnicalAgent(
            rule_config=_rule_config(
                "technical@1.0.0",
                ma5_gap_up_min=0.005,
                close_position_up_min=0.60,
                return_5d_up_min=0.010,
                ma5_gap_down_max=-0.005,
                close_position_down_max=0.40,
                return_5d_down_max=-0.010,
            ),
            weight=0.30,
        )
    )

    decision = adapter.decide(_context(_segment(phase="decide"), step_index=1))

    assert decision.proposals == ()


def test_decision_adapter_emits_decision_only_during_decide_phase() -> None:
    votes = (
        AgentVote("domestic_macro", "domestic_macro@1.0.0", "skip", 0.0, 0.2, 0.0, ()),
        AgentVote("flow", "flow@1.0.0", "up", 0.8, 0.25, 0.2, ()),
        AgentVote("technical", "technical@1.0.0", "up", 0.7, 0.3, 0.21, ()),
        AgentVote("valuation", "valuation@1.0.0", "skip", 0.0, 0.1, 0.0, ()),
        AgentVote("volatility", "volatility@1.0.0", "skip", 0.0, 0.15, 0.0, ()),
    )
    adapter = DecisionAgentAdapter(
        agent=DecisionAgent(
            threshold_up=ThresholdsConfig(up=0.25, down=-0.25).up,
            threshold_down=ThresholdsConfig(up=0.25, down=-0.25).down,
            config_signature="config-signature",
        )
    )

    active = adapter.decide(_context(_segment(phase="decide", votes=votes), step_index=1))
    inactive = adapter.decide(_context(_segment(phase="vote", votes=votes), step_index=0))

    assert len(active.proposals) == 1
    assert active.proposals[0].actor_id == "decision"
    assert active.proposals[0].payload["decision_result"]
    assert inactive.proposals == ()


def test_adapter_helpers_reject_invalid_segment_shape_and_features() -> None:
    invalid_state = SimulationState(
        step_index=0,
        seed=Seed(7),
        snapshot_ref=SnapshotRef(
            snapshot_id=UUID("11111111-1111-1111-1111-111111111111"),
            tier="gold",
            storage_key="data/gold/features.parquet",
        ),
        segments=(_segment(phase="vote"), _segment(phase="vote")),
        participants=(KospiDecisionParticipant(participant_id="market-kospi"),),
        pending_actions=(),
    )
    invalid_context = AgentContext(
        scenario_key="kospi.next_day",
        agent_id="test-agent",
        step_index=0,
        seed=Seed(7),
        state=invalid_state,
    )
    missing_as_of_context = _context(
        KospiDecisionSegment(
            segment_id="segment-kospi",
            participant_ids=("market-kospi",),
            phase="vote",
            decision_date=date(2025, 2, 14),
            snapshot_id="snapshot-2025-02-13",
            features_row={"foreign_net_buy_krw_5d_sum": 1.0},
            votes=(),
            decision_result=None,
        ),
        step_index=0,
    )

    with pytest.raises(ValueError, match="exactly one scenario segment"):
        _ = adapter_module._active_segment(invalid_context)

    with pytest.raises(ValueError, match="include as_of_date"):
        _ = adapter_module._extract_as_of_date({})

    with pytest.raises(ValueError, match="must be a feature value"):
        _ = adapter_module._feature_values_only({"kospi_return_1d": object()}, ("kospi_return_1d",))

    flow_adapter = FlowAgentAdapter(
        agent=FlowAgent(
            rule_config=_rule_config(
                "flow@1.0.0",
                foreign_pct_up_min=0.010,
                foreign_pct_down_max=-0.010,
                foreign_pct_neutral_abs_max=0.003,
            ),
            weight=0.25,
        )
    )
    with pytest.raises(ValueError, match="include as_of_date"):
        _ = flow_adapter.decide(missing_as_of_context)
