from __future__ import annotations

from kospi_decision_pipeline_core import __version__
from kospi_decision_pipeline_core.ids import dataset_id
from kospi_decision_pipeline_core.io import ensure_directory
from kospi_decision_pipeline_core.schemas import (
    DecisionRecord,
    FeatureRecord,
    ScenarioConfig,
    ScenarioRuntimeConfig,
)
from kospi_decision_pipeline_core.types import Decision


def test_core_version() -> None:
    assert __version__ == "0.0.1"


def test_dataset_id() -> None:
    assert dataset_id("gold") == "dataset:gold"


def test_ensure_directory_creates_path(tmp_path) -> None:
    target = tmp_path / "nested"

    assert ensure_directory(target) == target
    assert target.is_dir()


def test_decision_dataclass() -> None:
    decision = Decision(label="up", score=0.5)

    assert decision.label == "up"
    assert decision.score == 0.5


def test_schema_stubs_are_instantiable() -> None:
    assert isinstance(DecisionRecord(), DecisionRecord)
    assert isinstance(FeatureRecord(), FeatureRecord)
    assert isinstance(
        ScenarioConfig(
            scenario_id="kospi.next_day",
            horizon="next_day",
            agents=("technical", "decision"),
            runtime=ScenarioRuntimeConfig(
                agents_config_path="apps/kr-kospi/config/agents.yaml",
                features_path="data/gold/features.parquet",
                output_dir="data/decisions",
            ),
        ),
        ScenarioConfig,
    )
