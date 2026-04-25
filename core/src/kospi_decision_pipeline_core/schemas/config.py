from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from math import isclose
from pathlib import Path
import re
from types import MappingProxyType
from typing import Final, Literal, TypedDict, cast

import yaml


AgentId = Literal[
    "technical",
    "domestic_macro",
    "flow",
    "valuation",
    "volatility",
    "decision",
]
KNOWN_AGENT_IDS: Final[frozenset[str]] = frozenset(
    {
        "technical",
        "domestic_macro",
        "flow",
        "valuation",
        "volatility",
        "decision",
    }
)
WEIGHT_TOLERANCE: Final[float] = 1e-9


class ThresholdsConfigDict(TypedDict):
    up: float
    down: float


class ScenarioConfigDict(TypedDict):
    scenario_id: str
    horizon: Literal["next_day"]
    agents: list[str]


class _AgentsConfigRequiredDict(TypedDict):
    weights: dict[str, float]
    thresholds: ThresholdsConfigDict
    agents: dict[str, "AgentRuleConfigDict"]


class AgentsConfigDict(_AgentsConfigRequiredDict):
    pass


class AgentRuleConfigDict(TypedDict):
    rule_version: str
    thresholds: dict[str, float]


@dataclass(frozen=True, slots=True)
class AgentWeightConfig:
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        weights = _normalize_float_mapping(self.values, context="weights")
        _validate_known_agent_ids(weights.keys(), context="weights")
        total = sum(weights.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=WEIGHT_TOLERANCE):
            raise ValueError("weights must sum to 1.0 ± 1e-9")
        object.__setattr__(self, "values", MappingProxyType(dict(weights)))

    def to_dict(self) -> dict[str, float]:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class ThresholdsConfig:
    up: float
    down: float

    def __post_init__(self) -> None:
        up = _ensure_float(self.up, context="up")
        down = _ensure_float(self.down, context="down")
        if up <= down:
            raise ValueError("threshold up must be greater than threshold down")
        object.__setattr__(self, "up", up)
        object.__setattr__(self, "down", down)

    def to_dict(self) -> ThresholdsConfigDict:
        return {"up": self.up, "down": self.down}


@dataclass(frozen=True, slots=True)
class AgentRuleConfig:
    rule_version: str
    thresholds: Mapping[str, float]

    def __post_init__(self) -> None:
        rule_version = _ensure_string(self.rule_version, context="rule_version")
        if rule_version == "":
            raise ValueError("rule_version must be a non-empty string")
        object.__setattr__(self, "rule_version", rule_version)
        object.__setattr__(
            self,
            "thresholds",
            MappingProxyType(dict(_normalize_float_mapping(self.thresholds, context="thresholds"))),
        )

    def to_dict(self) -> AgentRuleConfigDict:
        return {
            "rule_version": self.rule_version,
            "thresholds": dict(self.thresholds),
        }


@dataclass(frozen=True, slots=True)
class AgentsConfig:
    weights: AgentWeightConfig
    thresholds: ThresholdsConfig
    agents: Mapping[str, AgentRuleConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        agent_configs = _normalize_agent_rules_mapping(self.agents, context="agents")
        _validate_matching_agent_keys(self.weights.values.keys(), agent_configs.keys())
        object.__setattr__(self, "agents", MappingProxyType(dict(agent_configs)))

    def to_dict(self) -> AgentsConfigDict:
        return {
            "weights": self.weights.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "agents": {
                agent_name: agent_config.to_dict()
                for agent_name, agent_config in self.agents.items()
            },
        }


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    scenario_id: str
    horizon: Literal["next_day"]
    agents: tuple[str, ...]

    def __post_init__(self) -> None:
        scenario_id = _ensure_string(self.scenario_id, context="scenario_id")
        if self.horizon != "next_day":
            raise ValueError("horizon must be 'next_day'")
        agent_ids = tuple(_normalize_string_sequence(self.agents, context="agents"))
        _validate_known_agent_ids(agent_ids, context="agents")
        object.__setattr__(self, "scenario_id", scenario_id)
        object.__setattr__(self, "agents", agent_ids)

    def to_dict(self) -> ScenarioConfigDict:
        return {
            "scenario_id": self.scenario_id,
            "horizon": self.horizon,
            "agents": list(self.agents),
        }


def load_agents_config(path: Path) -> AgentsConfig:
    payload = _load_yaml_mapping(path)
    weights_payload = _require_mapping(payload, "weights")
    thresholds_payload = _require_mapping(payload, "thresholds")
    if "agents" not in payload:
        raise ValueError("agents block is required")
    agents_payload = _require_mapping(payload, "agents")

    weights = AgentWeightConfig(_normalize_float_mapping(weights_payload, context="weights"))
    _validate_matching_agent_keys(weights.values.keys(), agents_payload.keys())

    thresholds = ThresholdsConfig(
        up=_require_float(thresholds_payload, "up"),
        down=_require_float(thresholds_payload, "down"),
    )
    return AgentsConfig(
        weights=weights,
        thresholds=thresholds,
        agents=_load_agent_rules(agents_payload),
    )


def load_scenario_config(path: Path) -> ScenarioConfig:
    payload = _load_yaml_mapping(path)
    agents_payload = _require_sequence(payload, "agents")

    return ScenarioConfig(
        scenario_id=_require_string(payload, "scenario_id"),
        horizon=_require_horizon(payload),
        agents=tuple(_normalize_string_sequence(agents_payload, context="agents")),
    )


def _load_yaml_mapping(path: Path) -> Mapping[str, object]:
    loaded = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    return _ensure_mapping(loaded, context=str(path))


def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    return _ensure_mapping(payload[key], context=key)


def _require_sequence(payload: Mapping[str, object], key: str) -> Sequence[object]:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    return _ensure_sequence(payload[key], context=key)


def _require_string(payload: Mapping[str, object], key: str) -> str:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    return _ensure_string(payload[key], context=key)


def _require_float(payload: Mapping[str, object], key: str) -> float:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    return _ensure_float(payload[key], context=key)


def _require_horizon(payload: Mapping[str, object]) -> Literal["next_day"]:
    horizon = _require_string(payload, "horizon")
    if horizon != "next_day":
        raise ValueError("horizon must be 'next_day'")
    return "next_day"


def _ensure_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    for raw_key in cast(Iterable[object], value.keys()):
        if not isinstance(raw_key, str):
            raise ValueError(f"{context} keys must be strings")
    return cast(Mapping[str, object], value)


def _ensure_sequence(value: object, context: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{context} must be a sequence")
    return value


def _ensure_string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _ensure_float(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be a float")
    return float(value)


def _normalize_float_mapping(value: object, context: str) -> dict[str, float]:
    payload = _ensure_mapping(value, context=context)
    return {
        key: _ensure_float(raw_value, context=f"{context}.{key}")
        for key, raw_value in payload.items()
    }


def _normalize_string_sequence(value: object, context: str) -> tuple[str, ...]:
    sequence = _ensure_sequence(value, context=context)
    return tuple(_ensure_string(item, context=f"{context}[]") for item in sequence)


def _normalize_agent_rules_mapping(value: object, context: str) -> dict[str, AgentRuleConfig]:
    payload = _ensure_mapping(value, context=context)
    return {
        agent_name: _ensure_agent_rule_config(agent_rule_config, context=f"{context}.{agent_name}")
        for agent_name, agent_rule_config in payload.items()
    }


def _ensure_agent_rule_config(value: object, context: str) -> AgentRuleConfig:
    if not isinstance(value, AgentRuleConfig):
        raise ValueError(f"{context} must be an AgentRuleConfig")
    return value


def _load_agent_rules(payload: Mapping[str, object]) -> dict[str, AgentRuleConfig]:
    _validate_known_agent_ids(payload.keys(), context="agents")
    rule_configs: dict[str, AgentRuleConfig] = {}
    for agent_name, agent_payload in payload.items():
        agent_mapping = _ensure_mapping(agent_payload, context=f"agents.{agent_name}")
        rule_version = _require_string(agent_mapping, "rule_version")
        _validate_rule_version(agent_name, rule_version)
        thresholds = _require_mapping(agent_mapping, "thresholds")
        rule_configs[agent_name] = AgentRuleConfig(
            rule_version=rule_version,
            thresholds=_normalize_float_mapping(
                thresholds, context=f"agents.{agent_name}.thresholds"
            ),
        )
    return rule_configs


def _validate_matching_agent_keys(
    weights_agent_ids: Iterable[str], agents_agent_ids: Iterable[str]
) -> None:
    weights_keys = frozenset(weights_agent_ids)
    agents_keys = frozenset(agents_agent_ids)
    if weights_keys != agents_keys:
        raise ValueError("weights and agents must contain identical keys")


def _validate_rule_version(agent_name: str, rule_version: str) -> None:
    if not re.fullmatch(rf"{re.escape(agent_name)}@\d+\.\d+\.\d+", rule_version):
        raise ValueError(f"agents.{agent_name}.rule_version must match {agent_name}@<semver>")


def _validate_known_agent_ids(agent_ids: Iterable[str], context: str) -> None:
    unknown_agent_ids = sorted(
        agent_id for agent_id in agent_ids if agent_id not in KNOWN_AGENT_IDS
    )
    if unknown_agent_ids:
        raise ValueError(f"unknown agent ids in {context}: {', '.join(unknown_agent_ids)}")
