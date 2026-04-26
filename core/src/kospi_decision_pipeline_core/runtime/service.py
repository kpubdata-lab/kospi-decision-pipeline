from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol, cast

import pyarrow.parquet as pq
from abdp.agents import Agent
from abdp.scenario import ActionResolver
from abdp.scenario import ScenarioRunner

from kospi_decision_pipeline_core.agents import (
    DecisionAgent,
    DomesticMacroAgent,
    FlowAgent,
    TechnicalAgent,
    ValuationAgent,
    VolatilityAgent,
    compute_config_signature,
)
from kospi_decision_pipeline_core.features.leakage_guard import (
    LeakageError,
    assert_join_not_from_future,
    assert_no_forbidden_columns,
)
from kospi_decision_pipeline_core.schemas import DecisionResult
from kospi_decision_pipeline_core.schemas.config import load_agents_config, load_scenario_config
from kospi_decision_pipeline_core.schemas.serialization import to_jsonl_line

from .adapters import (
    DecisionAgentAdapter,
    DomesticMacroAgentAdapter,
    FlowAgentAdapter,
    TechnicalAgentAdapter,
    ValuationAgentAdapter,
    VolatilityAgentAdapter,
)
from .scenario import KospiNextDayScenario, KospiScenarioResolver
from .models import KospiActionProposal, KospiDecisionParticipant, KospiDecisionSegment


class _ArrowTable(Protocol):
    def to_pylist(self) -> list[dict[str, object]]: ...


class _ReadTable(Protocol):
    def __call__(self, source: Path) -> _ArrowTable: ...


READ_TABLE = cast(_ReadTable, getattr(pq, "read_table"))


def run_kospi_scenario(
    scenario_path: Path | str,
    decision_date: date,
    features_path: Path | None = None,
    output_dir: Path | None = None,
) -> DecisionResult:
    scenario_config_path = Path(scenario_path)
    scenario_config = load_scenario_config(scenario_config_path)
    runtime = scenario_config.runtime
    resolved_agents_path = _resolve_path(
        scenario_config_path,
        runtime.agents_config_path,
        override_path=None,
    )
    resolved_features_path = _resolve_path(
        scenario_config_path,
        runtime.features_path,
        override_path=features_path,
    )
    resolved_output_dir = _resolve_path(
        scenario_config_path,
        runtime.output_dir,
        override_path=output_dir,
    )
    agents_config = load_agents_config(resolved_agents_path)
    features_row = _load_features_row(resolved_features_path, decision_date)
    snapshot_id = _resolve_snapshot_id(features_row)

    scenario = KospiNextDayScenario(
        scenario_id=scenario_config.scenario_id,
        decision_date=decision_date,
        snapshot_id=snapshot_id,
        features_row=features_row,
        storage_key=str(resolved_features_path),
    )
    agents = cast(
        tuple[Agent[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal], ...],
        (
            TechnicalAgentAdapter(
                agent=TechnicalAgent(
                    rule_config=agents_config.agents["technical"],
                    weight=agents_config.weights.values["technical"],
                )
            ),
            DomesticMacroAgentAdapter(
                agent=DomesticMacroAgent(
                    rule_config=agents_config.agents["domestic_macro"],
                    weight=agents_config.weights.values["domestic_macro"],
                )
            ),
            FlowAgentAdapter(
                agent=FlowAgent(
                    rule_config=agents_config.agents["flow"],
                    weight=agents_config.weights.values["flow"],
                )
            ),
            ValuationAgentAdapter(
                agent=ValuationAgent(
                    rule_config=agents_config.agents["valuation"],
                    weight=agents_config.weights.values["valuation"],
                )
            ),
            VolatilityAgentAdapter(
                agent=VolatilityAgent(
                    rule_config=agents_config.agents["volatility"],
                    weight=agents_config.weights.values["volatility"],
                )
            ),
            DecisionAgentAdapter(
                agent=DecisionAgent(
                    threshold_up=agents_config.thresholds.up,
                    threshold_down=agents_config.thresholds.down,
                    config_signature=compute_config_signature(resolved_agents_path),
                )
            ),
        ),
    )
    resolver = cast(
        ActionResolver[KospiDecisionSegment, KospiDecisionParticipant, KospiActionProposal],
        KospiScenarioResolver(),
    )
    runner = ScenarioRunner(
        agents=agents,
        resolver=resolver,
        max_steps=2,
    )
    run = runner.run(scenario)
    final_segment = run.final_state.segments[0]
    if final_segment.decision_result is None:
        raise ValueError("scenario did not produce a final decision result")
    _persist_decision_result(
        final_segment.decision_result, resolved_output_dir, scenario_config.scenario_id
    )
    return final_segment.decision_result


def _resolve_path(base_path: Path, configured_path: str, override_path: Path | None) -> Path:
    if override_path is not None:
        return override_path
    configured = Path(configured_path)
    if configured.is_absolute():
        return configured
    return _workspace_root(base_path) / configured


def _workspace_root(base_path: Path) -> Path:
    resolved = base_path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return resolved.parent


def _load_features_row(features_path: Path, decision_date: date) -> dict[str, object]:
    rows = READ_TABLE(features_path).to_pylist()
    matching_rows = _matching_rows(rows, decision_date)
    if len(matching_rows) != 1:
        raise ValueError("expected exactly one features row for the requested decision_date")
    row = dict(matching_rows[0])
    _assert_lag_safe_row(row, decision_date)
    assert_no_forbidden_columns(row.keys())
    return row


def _matching_rows(rows: list[dict[str, object]], decision_date: date) -> list[dict[str, object]]:
    if rows and all("decision_date" in row for row in rows):
        return [row for row in rows if row.get("decision_date") == decision_date]
    target_as_of = _previous_trading_day(decision_date)
    return [row for row in rows if row.get("as_of_date", row.get("trade_date")) == target_as_of]


def _assert_lag_safe_row(row: dict[str, object], decision_date: date) -> None:
    if "as_of_date" in row or "trade_date" in row:
        joined_as_of = row.get("as_of_date", row.get("trade_date"))
        if not isinstance(joined_as_of, date):
            raise LeakageError("features row must include a valid as_of_date")
        assert_join_not_from_future(joined_as_of=joined_as_of, decision_date=decision_date)
        if joined_as_of >= decision_date:
            raise LeakageError("features row must be strictly earlier than decision_date")


def _previous_trading_day(decision_date: date) -> date:
    current = decision_date - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _resolve_snapshot_id(row: dict[str, object]) -> str:
    raw_snapshot_id = row.get("snapshot_id")
    if isinstance(raw_snapshot_id, str) and raw_snapshot_id != "":
        return raw_snapshot_id
    canonical = "|".join(f"{key}={row[key]}" for key in sorted(row))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    as_of_value = row.get("as_of_date", row.get("trade_date"))
    if isinstance(as_of_value, date):
        return f"gold:{as_of_value.isoformat()}:{digest}"
    return f"gold:{digest}"


def _persist_decision_result(result: DecisionResult, output_dir: Path, scenario_id: str) -> None:
    output_path = output_dir / scenario_id / f"{result.decision_date.isoformat()}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(to_jsonl_line(result) + "\n", encoding="utf-8")


__all__ = ["run_kospi_scenario"]
