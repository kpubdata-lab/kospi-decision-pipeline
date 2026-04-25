from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

import pytest
import yaml

from kospi_decision_pipeline_core.schemas.config import (
    AgentRuleConfig,
    AgentWeightConfig,
    AgentsConfig,
    ScenarioConfig,
    ThresholdsConfig,
    load_agents_config,
    load_scenario_config,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_CONFIG_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "agents.yaml"
SCENARIO_CONFIG_PATH = REPO_ROOT / "apps" / "kr-kospi" / "config" / "scenario.kospi.next_day.yaml"


def write_yaml(path: Path, content: object) -> Path:
    _ = path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return path


def valid_agents_payload() -> dict[str, object]:
    return {
        "weights": {
            "technical": 0.30,
            "domestic_macro": 0.20,
            "flow": 0.25,
            "valuation": 0.10,
            "volatility": 0.15,
        },
        "thresholds": {"up": 0.25, "down": -0.25},
        "agents": {
            "technical": {
                "rule_version": "technical@1.0.0",
                "thresholds": {
                    "ma5_gap_up_min": 0.005,
                    "close_position_up_min": 0.60,
                    "return_5d_up_min": 0.010,
                    "ma5_gap_down_max": -0.005,
                    "close_position_down_max": 0.40,
                    "return_5d_down_max": -0.010,
                },
            },
            "domestic_macro": {
                "rule_version": "domestic_macro@1.0.0",
                "thresholds": {
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
            },
            "flow": {
                "rule_version": "flow@1.0.0",
                "thresholds": {
                    "foreign_pct_up_min": 0.010,
                    "foreign_pct_down_max": -0.010,
                    "foreign_pct_neutral_abs_max": 0.003,
                },
            },
            "valuation": {
                "rule_version": "valuation@1.0.0",
                "thresholds": {
                    "per_percentile_up_max": 0.30,
                    "pbr_percentile_up_max": 0.30,
                    "per_percentile_down_min": 0.70,
                    "pbr_percentile_down_min": 0.70,
                    "fair_value_center": 0.50,
                    "fair_value_half_band": 0.10,
                },
            },
            "volatility": {
                "rule_version": "volatility@1.0.0",
                "thresholds": {
                    "realized_vol_20d_up_max": 0.18,
                    "realized_vol_pct_up_max": 0.30,
                    "atr_14d_up_max": 35.0,
                    "realized_vol_pct_down_min": 0.80,
                    "realized_vol_20d_down_min": 0.25,
                    "atr_14d_down_min": 45.0,
                    "realized_vol_pct_mid_low": 0.30,
                    "realized_vol_pct_mid_high": 0.80,
                },
            },
        },
    }


def valid_agent_rules() -> dict[str, AgentRuleConfig]:
    payload = cast(dict[str, dict[str, object]], valid_agents_payload()["agents"])
    return {
        agent_name: AgentRuleConfig(
            rule_version=cast(str, agent_payload["rule_version"]),
            thresholds=cast(dict[str, float], agent_payload["thresholds"]),
        )
        for agent_name, agent_payload in payload.items()
    }


def test_config_dataclasses_construct_and_serialize() -> None:
    weights = AgentWeightConfig(
        {
            "technical": 0.30,
            "domestic_macro": 0.20,
            "flow": 0.25,
            "valuation": 0.10,
            "volatility": 0.15,
        }
    )
    thresholds = ThresholdsConfig(up=0.25, down=-0.25)
    config = AgentsConfig(
        weights=weights,
        thresholds=thresholds,
        agents=valid_agent_rules(),
    )
    scenario = ScenarioConfig(
        scenario_id="kospi.next_day",
        horizon="next_day",
        agents=(
            "technical",
            "domestic_macro",
            "flow",
            "valuation",
            "volatility",
            "decision",
        ),
    )

    assert config.to_dict() == {
        "weights": {
            "technical": 0.30,
            "domestic_macro": 0.20,
            "flow": 0.25,
            "valuation": 0.10,
            "volatility": 0.15,
        },
        "thresholds": {"up": 0.25, "down": -0.25},
        "agents": cast(dict[str, object], valid_agents_payload()["agents"]),
    }
    assert scenario.to_dict() == {
        "scenario_id": "kospi.next_day",
        "horizon": "next_day",
        "agents": [
            "technical",
            "domestic_macro",
            "flow",
            "valuation",
            "volatility",
            "decision",
        ],
    }


def test_agent_rule_config_thresholds_are_immutable() -> None:
    rule_config = AgentRuleConfig(
        rule_version="technical@1.0.0",
        thresholds={"ma5_gap_up_min": 0.005},
    )

    with pytest.raises(TypeError):
        cast(dict[str, float], rule_config.thresholds)["ma5_gap_up_min"] = 0.010


def test_agent_rule_config_rejects_empty_rule_version() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        _ = AgentRuleConfig(rule_version="", thresholds={"ma5_gap_up_min": 0.005})


def test_agents_config_rejects_mismatched_weight_and_agent_names_when_constructed_directly() -> (
    None
):
    with pytest.raises(ValueError, match="weights and agents must contain identical keys"):
        _ = AgentsConfig(
            weights=AgentWeightConfig({"technical": 0.60, "flow": 0.40}),
            thresholds=ThresholdsConfig(up=0.25, down=-0.25),
            agents={
                "technical": AgentRuleConfig(
                    rule_version="technical@1.0.0",
                    thresholds={"ma5_gap_up_min": 0.005},
                )
            },
        )


def test_agents_config_rejects_non_agent_rule_config_entries_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="agents.technical must be an AgentRuleConfig"):
        _ = AgentsConfig(
            weights=AgentWeightConfig({"technical": 1.0}),
            thresholds=ThresholdsConfig(up=0.25, down=-0.25),
            agents=cast(
                dict[str, AgentRuleConfig],
                {"technical": cast(AgentRuleConfig, object())},
            ),
        )


def test_agent_weight_config_rejects_sum_not_equal_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        _ = AgentWeightConfig({"technical": 0.6, "flow": 0.3})


def test_thresholds_config_rejects_invalid_ordering() -> None:
    with pytest.raises(ValueError, match="up.*greater than.*down"):
        _ = ThresholdsConfig(up=0.10, down=0.10)


def test_thresholds_config_rejects_non_float_values_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="up must be a float"):
        _ = ThresholdsConfig(up=True, down=-0.25)


def test_scenario_config_rejects_invalid_horizon_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="next_day"):
        _ = ScenarioConfig(
            scenario_id="kospi.weekly",
            horizon=cast(Literal["next_day"], cast(object, "weekly")),
            agents=("technical", "decision"),
        )


def test_scenario_config_rejects_non_string_scenario_id_when_constructed_directly() -> None:
    with pytest.raises(ValueError, match="scenario_id must be a string"):
        _ = ScenarioConfig(
            scenario_id=cast(str, cast(object, 1)),
            horizon="next_day",
            agents=("technical", "decision"),
        )


def test_load_agents_config_rejects_unknown_agent_ids(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    weights = cast(dict[str, float], payload["weights"])
    agents = cast(dict[str, object], payload["agents"])
    weights["mystery"] = 0.15
    weights["technical"] = 0.15
    del agents["technical"]
    agents["mystery"] = {
        "rule_version": "mystery@1.0.0",
        "thresholds": {"mystery_threshold": 1.0},
    }
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="unknown agent"):
        _ = load_agents_config(config_path)


def test_load_scenario_config_rejects_invalid_horizon(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "scenario.yaml",
        {
            "scenario_id": "kospi.weekly",
            "horizon": "weekly",
            "agents": ["technical", "decision"],
        },
    )

    with pytest.raises(ValueError, match="next_day"):
        _ = load_scenario_config(config_path)


def test_load_scenario_config_rejects_unknown_agent_ids(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "scenario.yaml",
        {
            "scenario_id": "kospi.next_day",
            "horizon": "next_day",
            "agents": ["technical", "mystery"],
        },
    )

    with pytest.raises(ValueError, match="unknown agent"):
        _ = load_scenario_config(config_path)


def test_load_agents_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_path = write_yaml(tmp_path / "agents.yaml", ["not", "a", "mapping"])

    with pytest.raises(ValueError, match="must be a mapping"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_non_string_weight_keys(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    payload["weights"] = {1: 0.50, "flow": 0.50}
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="keys must be strings"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_missing_threshold_value(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    payload["thresholds"] = {"down": -0.25}
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="up"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_non_float_threshold_value(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    payload["thresholds"] = {"up": "high", "down": -0.25}
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="up must be a float"):
        _ = load_agents_config(config_path)


def test_load_agents_config_parses_agents_block(tmp_path: Path) -> None:
    config_path = write_yaml(tmp_path / "agents.yaml", valid_agents_payload())

    loaded = load_agents_config(config_path)

    assert loaded.thresholds.to_dict() == {"up": 0.25, "down": -0.25}
    assert loaded.agents["technical"].rule_version == "technical@1.0.0"
    assert loaded.agents["technical"].thresholds["ma5_gap_up_min"] == 0.005
    assert loaded.to_dict() == cast(dict[str, object], valid_agents_payload())


def test_load_agents_config_rejects_missing_agents_block(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    del payload["agents"]
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="^agents block is required$"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_mismatched_agent_names_between_weights_and_agents(
    tmp_path: Path,
) -> None:
    payload = valid_agents_payload()
    weights = cast(dict[str, float], payload["weights"])
    _ = weights.pop("volatility")
    weights["decision"] = 0.15
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="weights and agents must contain identical keys"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_invalid_rule_version_format(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    agents = cast(dict[str, dict[str, object]], payload["agents"])
    agents["technical"]["rule_version"] = "flow@1.0.0"
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="rule_version"):
        _ = load_agents_config(config_path)


def test_load_agents_config_rejects_non_numeric_agent_threshold_value(tmp_path: Path) -> None:
    payload = valid_agents_payload()
    agents = cast(dict[str, dict[str, object]], payload["agents"])
    thresholds = cast(dict[str, object], agents["technical"]["thresholds"])
    thresholds["ma5_gap_up_min"] = "high"
    config_path = write_yaml(tmp_path / "agents.yaml", payload)

    with pytest.raises(ValueError, match="agents.technical.thresholds.ma5_gap_up_min"):
        _ = load_agents_config(config_path)


def test_load_agents_config_exposes_immutable_agent_threshold_mapping(tmp_path: Path) -> None:
    config_path = write_yaml(tmp_path / "agents.yaml", valid_agents_payload())

    loaded = load_agents_config(config_path)

    with pytest.raises(TypeError):
        cast(dict[str, float], loaded.agents["technical"].thresholds)["ma5_gap_up_min"] = 0.010


def test_load_scenario_config_rejects_non_string_scenario_id(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "scenario.yaml",
        {
            "scenario_id": 1,
            "horizon": "next_day",
            "agents": ["technical", "decision"],
        },
    )

    with pytest.raises(ValueError, match="scenario_id must be a string"):
        _ = load_scenario_config(config_path)


def test_load_scenario_config_rejects_missing_scenario_id(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "scenario.yaml",
        {
            "horizon": "next_day",
            "agents": ["technical", "decision"],
        },
    )

    with pytest.raises(ValueError, match="scenario_id"):
        _ = load_scenario_config(config_path)


def test_load_scenario_config_rejects_non_sequence_agents(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "scenario.yaml",
        {
            "scenario_id": "kospi.next_day",
            "horizon": "next_day",
            "agents": "technical",
        },
    )

    with pytest.raises(ValueError, match="agents must be a sequence"):
        _ = load_scenario_config(config_path)


@pytest.mark.parametrize(
    ("filename", "content", "loader", "missing_key"),
    [
        (
            "agents.yaml",
            {"thresholds": {"up": 0.25, "down": -0.25}, "agents": {}},
            load_agents_config,
            "weights",
        ),
        (
            "scenario.yaml",
            {"scenario_id": "kospi.next_day", "horizon": "next_day"},
            load_scenario_config,
            "agents",
        ),
    ],
)
def test_loaders_reject_missing_required_keys(
    tmp_path: Path,
    filename: str,
    content: object,
    loader: Callable[[Path], object],
    missing_key: str,
) -> None:
    config_path = write_yaml(tmp_path / filename, content)

    with pytest.raises(ValueError, match=missing_key):
        _ = loader(config_path)


def test_agents_config_round_trip(tmp_path: Path) -> None:
    loaded = load_agents_config(AGENTS_CONFIG_PATH)
    round_trip_path = write_yaml(tmp_path / "agents.roundtrip.yaml", loaded.to_dict())

    assert load_agents_config(round_trip_path) == loaded


def test_scenario_config_round_trip(tmp_path: Path) -> None:
    loaded = load_scenario_config(SCENARIO_CONFIG_PATH)
    round_trip_path = write_yaml(tmp_path / "scenario.roundtrip.yaml", loaded.to_dict())

    assert load_scenario_config(round_trip_path) == loaded


def test_default_config_files_load_successfully() -> None:
    agents_config = load_agents_config(AGENTS_CONFIG_PATH)
    scenario_config = load_scenario_config(SCENARIO_CONFIG_PATH)

    assert agents_config.to_dict() == {
        "weights": {
            "technical": 0.30,
            "domestic_macro": 0.20,
            "flow": 0.25,
            "valuation": 0.10,
            "volatility": 0.15,
        },
        "thresholds": {"up": 0.25, "down": -0.25},
        "agents": cast(dict[str, object], valid_agents_payload()["agents"]),
    }
    assert scenario_config.to_dict() == {
        "scenario_id": "kospi.next_day",
        "horizon": "next_day",
        "agents": [
            "technical",
            "domestic_macro",
            "flow",
            "valuation",
            "volatility",
            "decision",
        ],
    }
