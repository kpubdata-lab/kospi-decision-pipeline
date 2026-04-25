from __future__ import annotations

from datetime import date

import pytest

from kospi_decision_pipeline_core.schemas.decisions import (
    AgentVote,
    BacktestRow,
    DecisionResult,
    EvidenceItem,
)
from kospi_decision_pipeline_core.schemas.serialization import (
    BACKTEST_CSV_FIELDS,
    from_jsonl_line,
    parse_agent_vote,
    parse_backtest_row,
    parse_decision_result,
    parse_evidence_item,
    to_csv_row,
    to_jsonl_line,
)


def make_decision_result() -> DecisionResult:
    evidence = EvidenceItem(
        name="volume_zscore",
        value=1.25,
        source="gold.features",
        as_of=date(2026, 4, 24),
    )
    vote = AgentVote(
        agent_name="technical",
        rule_version="technical@v1",
        label="up",
        score=0.72,
        weight=0.30,
        weighted_score=0.216,
        evidence=(evidence,),
    )
    return DecisionResult(
        decision_date=date(2026, 4, 25),
        label="up",
        aggregate_score=0.42,
        threshold_up=0.25,
        threshold_down=-0.25,
        votes=(vote,),
        config_signature="cfg:abc123",
        snapshot_id="snapshot:2026-04-25",
    )


def make_backtest_row() -> BacktestRow:
    return BacktestRow(
        decision_date=date(2026, 4, 25),
        label="down",
        aggregate_score=-0.41,
        ground_truth="down",
        next_day_return=-0.018,
        hit=True,
    )


def test_to_jsonl_line_is_deterministic_and_uses_declared_field_order() -> None:
    decision = make_decision_result()

    expected = (
        '{"decision_date":"2026-04-25","label":"up","aggregate_score":0.42,'
        '"threshold_up":0.25,"threshold_down":-0.25,"votes":[{"agent_name":"technical",'
        '"rule_version":"technical@v1","label":"up","score":0.72,"weight":0.3,'
        '"weighted_score":0.216,"evidence":[{"name":"volume_zscore","value":1.25,'
        '"source":"gold.features","as_of":"2026-04-24"}]}],'
        '"config_signature":"cfg:abc123","snapshot_id":"snapshot:2026-04-25"}'
    )

    assert to_jsonl_line(decision) == expected
    assert to_jsonl_line(decision) == expected


@pytest.mark.parametrize(
    "value",
    [
        make_decision_result(),
        make_backtest_row(),
        AgentVote(
            agent_name="technical",
            rule_version="technical@v1",
            label="up",
            score=0.72,
            weight=0.30,
            weighted_score=0.216,
            evidence=(
                EvidenceItem(
                    name="volume_zscore",
                    value=1.25,
                    source="gold.features",
                    as_of=date(2026, 4, 24),
                ),
            ),
        ),
        EvidenceItem(
            name="volume_zscore",
            value=1.25,
            source="gold.features",
            as_of=date(2026, 4, 24),
        ),
    ],
)
def test_jsonl_round_trip(value: object) -> None:
    assert from_jsonl_line(type(value), to_jsonl_line(value)) == value


def test_backtest_csv_fields_and_row_are_stable() -> None:
    row = make_backtest_row()

    assert BACKTEST_CSV_FIELDS == (
        "decision_date",
        "label",
        "aggregate_score",
        "ground_truth",
        "next_day_return",
        "hit",
    )
    assert to_csv_row(row, BACKTEST_CSV_FIELDS) == {
        "decision_date": "2026-04-25",
        "label": "down",
        "aggregate_score": "-0.41",
        "ground_truth": "down",
        "next_day_return": "-0.018",
        "hit": "true",
    }


def test_to_csv_row_rejects_nested_schema_objects() -> None:
    with pytest.raises(ValueError, match="flat BacktestRow"):
        _ = to_csv_row(make_decision_result(), BACKTEST_CSV_FIELDS)


def test_parse_helpers_reject_invalid_payloads() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _ = parse_evidence_item("[]")

    with pytest.raises(ValueError, match="votes must be a list"):
        _ = parse_decision_result(
            '{"decision_date":"2026-04-25","label":"up","aggregate_score":0.42,'
            '"threshold_up":0.25,"threshold_down":-0.25,"votes":{},'
            '"config_signature":"cfg:abc123","snapshot_id":"snapshot:2026-04-25"}'
        )

    with pytest.raises(ValueError, match="evidence must be a list"):
        _ = parse_agent_vote(
            '{"agent_name":"technical","rule_version":"technical@v1","label":"up",'
            '"score":0.72,"weight":0.3,"weighted_score":0.216,"evidence":{}}'
        )

    with pytest.raises(ValueError, match="unsupported schema type"):
        _ = from_jsonl_line(str, '"value"')


def test_parse_backtest_row_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="missing required key: hit"):
        _ = parse_backtest_row(
            '{"decision_date":"2026-04-25","label":"down","aggregate_score":-0.41,'
            '"ground_truth":"down","next_day_return":-0.018}'
        )
