from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import cast, overload

from .backtest import BacktestRow
from .decisions import (
    AgentVote,
    DecisionResult,
    EvidenceItem,
    GroundTruthLabel,
    ModelLabel,
)

BACKTEST_CSV_FIELDS: tuple[str, ...] = (
    "fold_id",
    "decision_date",
    "label",
    "aggregate_score",
    "target_label",
    "correct",
    "snapshot_id",
    "config_signature",
)


@overload
def from_jsonl_line(schema_type: type[EvidenceItem], line: str) -> EvidenceItem: ...


@overload
def from_jsonl_line(schema_type: type[AgentVote], line: str) -> AgentVote: ...


@overload
def from_jsonl_line(schema_type: type[DecisionResult], line: str) -> DecisionResult: ...


@overload
def from_jsonl_line(schema_type: type[BacktestRow], line: str) -> BacktestRow: ...


def from_jsonl_line(
    schema_type: type[EvidenceItem] | type[AgentVote] | type[DecisionResult] | type[BacktestRow],
    line: str,
) -> EvidenceItem | AgentVote | DecisionResult | BacktestRow:
    if schema_type is EvidenceItem:
        return parse_evidence_item(line)
    if schema_type is AgentVote:
        return parse_agent_vote(line)
    if schema_type is DecisionResult:
        return parse_decision_result(line)
    if schema_type is BacktestRow:
        return parse_backtest_row(line)
    raise ValueError(f"unsupported schema type: {schema_type}")


def to_jsonl_line(obj: EvidenceItem | AgentVote | DecisionResult | BacktestRow) -> str:
    return json.dumps(_to_json_value(obj), separators=(",", ":"), ensure_ascii=False)


def to_csv_row(obj: object, fields: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(obj, BacktestRow):
        raise ValueError("to_csv_row supports only flat BacktestRow values")
    if fields != BACKTEST_CSV_FIELDS:
        raise ValueError("fields must equal BACKTEST_CSV_FIELDS")
    return {field: _backtest_field_string(obj, field) for field in BACKTEST_CSV_FIELDS}


def parse_evidence_item(line: str) -> EvidenceItem:
    payload = _parse_json_object(line)
    return EvidenceItem(
        name=_require_string(payload, "name"),
        value=_require_float(payload, "value"),
        source=_require_string(payload, "source"),
        as_of=_require_date(payload, "as_of"),
    )


def parse_agent_vote(line: str) -> AgentVote:
    payload = _parse_json_object(line)
    evidence_payload = _require_list(payload, "evidence")
    return AgentVote(
        agent_name=_require_string(payload, "agent_name"),
        rule_version=_require_string(payload, "rule_version"),
        label=_require_model_label(payload, "label"),
        score=_require_float(payload, "score"),
        weight=_require_float(payload, "weight"),
        weighted_score=_require_float(payload, "weighted_score"),
        evidence=tuple(parse_evidence_item(_dump_json(item)) for item in evidence_payload),
    )


def parse_decision_result(line: str) -> DecisionResult:
    payload = _parse_json_object(line)
    votes_payload = _require_list(payload, "votes")
    return DecisionResult(
        decision_date=_require_date(payload, "decision_date"),
        label=_require_model_label(payload, "label"),
        aggregate_score=_require_float(payload, "aggregate_score"),
        threshold_up=_require_float(payload, "threshold_up"),
        threshold_down=_require_float(payload, "threshold_down"),
        votes=tuple(parse_agent_vote(_dump_json(item)) for item in votes_payload),
        config_signature=_require_string(payload, "config_signature"),
        snapshot_id=_require_string(payload, "snapshot_id"),
    )


def parse_backtest_row(line: str) -> BacktestRow:
    payload = _parse_json_object(line)
    return BacktestRow(
        fold_id=_require_int(payload, "fold_id"),
        decision_date=_require_date(payload, "decision_date"),
        label=_require_model_label(payload, "label"),
        aggregate_score=_require_float(payload, "aggregate_score"),
        target_label=_require_ground_truth_label(payload, "target_label"),
        correct=_require_bool(payload, "correct"),
        snapshot_id=_require_string(payload, "snapshot_id"),
        config_signature=_require_string(payload, "config_signature"),
    )


def _to_json_value(
    obj: EvidenceItem | AgentVote | DecisionResult | BacktestRow,
) -> dict[str, object]:
    if isinstance(obj, EvidenceItem):
        return {
            "name": obj.name,
            "value": obj.value,
            "source": obj.source,
            "as_of": obj.as_of.isoformat(),
        }
    if isinstance(obj, AgentVote):
        return {
            "agent_name": obj.agent_name,
            "rule_version": obj.rule_version,
            "label": obj.label,
            "score": obj.score,
            "weight": obj.weight,
            "weighted_score": obj.weighted_score,
            "evidence": [_to_json_value(item) for item in obj.evidence],
        }
    if isinstance(obj, DecisionResult):
        return {
            "decision_date": obj.decision_date.isoformat(),
            "label": obj.label,
            "aggregate_score": obj.aggregate_score,
            "threshold_up": obj.threshold_up,
            "threshold_down": obj.threshold_down,
            "votes": [_to_json_value(item) for item in obj.votes],
            "config_signature": obj.config_signature,
            "snapshot_id": obj.snapshot_id,
        }
    return {
        "fold_id": obj.fold_id,
        "decision_date": obj.decision_date.isoformat(),
        "label": obj.label,
        "aggregate_score": obj.aggregate_score,
        "target_label": obj.target_label,
        "correct": obj.correct,
        "snapshot_id": obj.snapshot_id,
        "config_signature": obj.config_signature,
    }


def _parse_json_object(line: str) -> dict[str, object]:
    payload = cast(object, json.loads(line))
    if not isinstance(payload, Mapping):
        raise ValueError("JSON payload must be a JSON object")
    return {
        str(raw_key): value for raw_key, value in cast(Mapping[object, object], payload).items()
    }


def _require_value(payload: Mapping[str, object], key: str) -> object:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    return payload[key]


def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = _require_value(payload, key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_float(payload: Mapping[str, object], key: str) -> float:
    value = _require_value(payload, key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be a float")
    return float(value)


def _require_bool(payload: Mapping[str, object], key: str) -> bool:
    value = _require_value(payload, key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a bool")
    return value


def _require_int(payload: Mapping[str, object], key: str) -> int:
    value = _require_value(payload, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an int")
    return value


def _require_date(payload: Mapping[str, object], key: str) -> date:
    value = _require_string(payload, key)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date") from exc


def _require_list(payload: Mapping[str, object], key: str) -> list[object]:
    value = _require_value(payload, key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return cast(list[object], value)


def _require_model_label(payload: Mapping[str, object], key: str) -> ModelLabel:
    value = _require_string(payload, key)
    if value not in {"up", "down", "skip"}:
        raise ValueError(f"{key} must be one of: down, skip, up")
    return cast(ModelLabel, value)


def _require_ground_truth_label(payload: Mapping[str, object], key: str) -> GroundTruthLabel:
    value = _require_string(payload, key)
    if value not in {"up", "down", "flat"}:
        raise ValueError(f"{key} must be one of: down, flat, up")
    return cast(GroundTruthLabel, value)


def _dump_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _backtest_field_string(row: BacktestRow, field: str) -> str:
    if field == "fold_id":
        return str(row.fold_id)
    if field == "decision_date":
        return row.decision_date.isoformat()
    if field == "label":
        return row.label
    if field == "aggregate_score":
        return str(row.aggregate_score)
    if field == "target_label":
        return row.target_label
    if field == "correct":
        return "true" if row.correct else "false"
    if field == "snapshot_id":
        return row.snapshot_id
    return row.config_signature
