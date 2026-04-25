from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kospi_decision_pipeline_core.schemas.config import (
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
    path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return path


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
        rule_versions={"decision": "v1"},
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
        "rule_versions": {"decision": "v1"},
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


def test_agent_weight_config_rejects_sum_not_equal_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        AgentWeightConfig({"technical": 0.6, "flow": 0.3})


def test_thresholds_config_rejects_invalid_ordering() -> None:
    with pytest.raises(ValueError, match="up.*greater than.*down"):
        ThresholdsConfig(up=0.10, down=0.10)


def test_load_agents_config_rejects_unknown_agent_ids(tmp_path: Path) -> None:
    config_path = write_yaml(
        tmp_path / "agents.yaml",
        {
            "weights": {
                "technical": 0.50,
                "flow": 0.25,
                "mystery": 0.25,
            },
            "thresholds": {"up": 0.25, "down": -0.25},
        },
    )

    with pytest.raises(ValueError, match="unknown agent"):
        load_agents_config(config_path)


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
        load_scenario_config(config_path)


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
        load_scenario_config(config_path)


@pytest.mark.parametrize(
    ("filename", "content", "loader", "missing_key"),
    [
        (
            "agents.yaml",
            {"thresholds": {"up": 0.25, "down": -0.25}},
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
    loader: object,
    missing_key: str,
) -> None:
    config_path = write_yaml(tmp_path / filename, content)

    with pytest.raises(ValueError, match=missing_key):
        loader(config_path)


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
