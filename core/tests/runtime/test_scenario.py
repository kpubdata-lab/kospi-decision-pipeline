from __future__ import annotations

from datetime import date

import pytest

from kospi_decision_pipeline_core.runtime.models import ScenarioPhase
from kospi_decision_pipeline_core.schemas import (
    AgentVote,
    DecisionResult,
    EvidenceItem,
    ModelLabel,
)
from kospi_decision_pipeline_core.runtime.models import (
    DecisionResultProposal,
    KospiDecisionParticipant,
    KospiDecisionSegment,
    VoteProposal,
)
from kospi_decision_pipeline_core.runtime.scenario import (
    KospiNextDayScenario,
    KospiScenarioResolver,
)


def _evidence_item(name: str, value: float) -> EvidenceItem:
    return EvidenceItem(name=name, value=value, source="computed", as_of=date(2025, 2, 13))


def _vote(agent_name: str, label: ModelLabel = "skip") -> AgentVote:
    return AgentVote(
        agent_name=agent_name,
        rule_version=f"{agent_name}@1.0.0",
        label=label,
        score=0.0,
        weight=0.2,
        weighted_score=0.0,
        evidence=(_evidence_item("signal", 0.0),),
    )


def _decision_result(votes: tuple[AgentVote, ...]) -> DecisionResult:
    return DecisionResult(
        decision_date=date(2025, 2, 14),
        label="up",
        aggregate_score=0.55,
        threshold_up=0.25,
        threshold_down=-0.25,
        votes=votes,
        config_signature="config-signature",
        snapshot_id="snapshot-2025-02-13",
    )


def _segment(
    *,
    phase: ScenarioPhase = "vote",
    votes: tuple[AgentVote, ...] = (),
) -> KospiDecisionSegment:
    return KospiDecisionSegment(
        segment_id="segment-kospi",
        participant_ids=("market-kospi",),
        phase=phase,
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
        votes=votes,
        decision_result=None,
    )


def test_vote_phase_resolves_into_decide_phase_with_unique_votes() -> None:
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
    )
    state = scenario.build_initial_state()
    resolver = KospiScenarioResolver()
    proposals = (
        VoteProposal.from_vote(_vote("technical", "up"), step_index=0),
        VoteProposal.from_vote(_vote("domestic_macro", "skip"), step_index=0),
        VoteProposal.from_vote(_vote("flow", "up"), step_index=0),
        VoteProposal.from_vote(_vote("valuation", "down"), step_index=0),
        VoteProposal.from_vote(_vote("volatility", "skip"), step_index=0),
    )

    next_state = resolver.resolve(state, proposals)

    assert next_state.step_index == 1
    assert next_state.pending_actions == ()
    assert next_state.segments[0].phase == "decide"
    assert tuple(vote.agent_name for vote in next_state.segments[0].votes) == (
        "domestic_macro",
        "flow",
        "technical",
        "valuation",
        "volatility",
    )


def test_vote_phase_rejects_duplicate_or_missing_rule_votes() -> None:
    resolver = KospiScenarioResolver()
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
    )
    state = scenario.build_initial_state()

    duplicate_proposals = (
        VoteProposal.from_vote(_vote("technical"), step_index=0),
        VoteProposal.from_vote(_vote("technical"), step_index=0),
        VoteProposal.from_vote(_vote("flow"), step_index=0),
        VoteProposal.from_vote(_vote("valuation"), step_index=0),
        VoteProposal.from_vote(_vote("volatility"), step_index=0),
    )
    missing_proposals = duplicate_proposals[1:]

    with pytest.raises(ValueError, match="exactly 5 unique VoteProposals"):
        _ = resolver.resolve(state, duplicate_proposals)

    with pytest.raises(ValueError, match="exactly 5 unique VoteProposals"):
        _ = resolver.resolve(state, missing_proposals)


def test_vote_phase_rejects_decision_result_proposals() -> None:
    resolver = KospiScenarioResolver()
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
    )
    state = scenario.build_initial_state()
    votes = tuple(
        VoteProposal.from_vote(_vote(agent_name), step_index=0)
        for agent_name in ("technical", "domestic_macro", "flow", "valuation", "volatility")
    )
    decision = DecisionResultProposal.from_decision_result(
        _decision_result(tuple(proposal.vote for proposal in votes)),
        step_index=0,
    )

    with pytest.raises(ValueError, match="DecisionResultProposal"):
        _ = resolver.resolve(state, votes + (decision,))


def test_decide_phase_resolves_into_done_phase_with_single_decision_result() -> None:
    resolver = KospiScenarioResolver()
    votes = (
        _vote("technical", "up"),
        _vote("domestic_macro", "skip"),
        _vote("flow", "up"),
        _vote("valuation", "down"),
        _vote("volatility", "skip"),
    )
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
        initial_phase="decide",
        votes=votes,
    )
    state = scenario.build_initial_state()

    next_state = resolver.resolve(
        state,
        (DecisionResultProposal.from_decision_result(_decision_result(votes), step_index=1),),
    )

    assert next_state.step_index == 2
    assert next_state.pending_actions == ()
    assert next_state.segments[0].phase == "done"
    assert next_state.segments[0].decision_result == _decision_result(votes)


def test_decide_phase_rejects_non_single_decision_result() -> None:
    resolver = KospiScenarioResolver()
    votes = (
        _vote("technical"),
        _vote("domestic_macro"),
        _vote("flow"),
        _vote("valuation"),
        _vote("volatility"),
    )
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
        initial_phase="decide",
        votes=votes,
    )
    state = scenario.build_initial_state()
    decision = DecisionResultProposal.from_decision_result(_decision_result(votes), step_index=1)

    with pytest.raises(ValueError, match="exactly 1 DecisionResultProposal"):
        _ = resolver.resolve(state, ())

    with pytest.raises(ValueError, match="exactly 1 DecisionResultProposal"):
        _ = resolver.resolve(state, (decision, decision))


def test_scenario_builds_single_segment_and_participant() -> None:
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
    )

    state = scenario.build_initial_state()

    assert state.step_index == 0
    assert state.participants == (KospiDecisionParticipant(participant_id="market-kospi"),)
    assert state.segments[0] == _segment()


def test_resolver_rejects_invalid_terminal_or_multi_segment_state() -> None:
    resolver = KospiScenarioResolver()
    scenario = KospiNextDayScenario(
        scenario_id="kospi.next_day",
        decision_date=date(2025, 2, 14),
        snapshot_id="snapshot-2025-02-13",
        features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
    )
    state = scenario.build_initial_state()
    done_state = state.__class__(
        step_index=2,
        seed=state.seed,
        snapshot_ref=state.snapshot_ref,
        segments=(
            KospiDecisionSegment(
                segment_id="segment-kospi",
                participant_ids=("market-kospi",),
                phase="done",
                decision_date=date(2025, 2, 14),
                snapshot_id="snapshot-2025-02-13",
                features_row={"as_of_date": date(2025, 2, 13), "kospi_return_1d": 0.01},
                votes=(),
                decision_result=None,
            ),
        ),
        participants=state.participants,
        pending_actions=(),
    )
    multi_segment_state = state.__class__(
        step_index=0,
        seed=state.seed,
        snapshot_ref=state.snapshot_ref,
        segments=(state.segments[0], state.segments[0]),
        participants=state.participants,
        pending_actions=(),
    )

    with pytest.raises(ValueError, match="terminal phase"):
        _ = resolver.resolve(done_state, ())

    with pytest.raises(ValueError, match="exactly one scenario segment"):
        _ = resolver.resolve(multi_segment_state, ())
