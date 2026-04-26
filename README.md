# KOSPI Decision Pipeline

> **Disclaimer / 면책 고지**
>
> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental tool for research and education only. It is not investment advice or financial advisory.

Public-data-first ABDP-based KOSPI next-day direction prediction pipeline for research and education. The repository turns Korean public market and macro data into deterministic Bronze, Silver, and Gold datasets, scores five rule agents plus one decision aggregator through ABDP, and emits reproducible scenario and backtest artifacts with explicit scope boundaries.

## Status

[![Tests](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/test.yml/badge.svg)](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/test.yml)
[![Lint](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/lint.yml/badge.svg)](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/lint.yml)
[![Mypy](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/mypy.yml/badge.svg)](https://github.com/kpubdata-lab/kospi-decision-pipeline/actions/workflows/mypy.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green)

- Release target: **v0.1**
- Project posture: **research-grade, deterministic, public-data-first**
- Out of scope for v0.1: S&P 500, real-time FX, broker reports, individual stocks, production trading automation

## Architecture overview

```text
KRX / ECOS (+ optional KOSIS / Public Data Portal connector surfaces)
                |
                v
      Bronze raw parquet snapshots
                |
                v
       Silver typed normalized datasets
                |
                v
      Gold decision features parquet
                |
                v
TechnicalAgent   DomesticMacroAgent   FlowAgent   ValuationAgent   VolatilityAgent
        \              |                 |             |                /
         \             |                 |             |               /
          +------------+-----------------+-------------+--------------+
                                       |
                                       v
                       DecisionAgent weighted aggregation
                                       |
                                       v
                     ABDP ScenarioRunner / runtime service
                                       |
                    +------------------+------------------+
                    |                                     |
                    v                                     v
      decision JSONL artifacts                walk-forward backtest reports
```

## Quickstart

### Prerequisites

- Python 3.12+
- `uv`
- Fixture-backed local runs for documentation and CI-style dry runs
- API credentials for KRX, ECOS, and KOSIS only if live connectors are introduced later; the shipped v0.1 `LiveConnectorRegistry` is not yet implemented

Environment variables typically used for live runs depend on the upstream data client configuration. For safe automation, export the non-interactive shell settings used in CI:

```bash
export CI=true DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0 \
  GCM_INTERACTIVE=never HOMEBREW_NO_AUTO_UPDATE=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1
```

### Install

```bash
uv sync --extra dev
```

### Smoke-check the shipped command surface

These commands are safe to run on a fresh checkout and match the current CLI/runtime surface:

```bash
uv run --python 3.12 kospi-pipeline --help
uv run --python 3.12 kospi-pipeline ingest --help
uv run --python 3.12 kospi-pipeline build-features --help
uv run --python 3.12 python -c "from kospi_decision_pipeline_app_kr_kospi.transforms.target_labels import build_backtest_dataset; print(build_backtest_dataset.__name__)"
uv run --python 3.12 kospi-pipeline run-scenario --help
uv run --python 3.12 kospi-pipeline run-backtest --help
```

### End-to-end example

The shipped CLI implements `ingest`, `build-features`, `run-scenario`, and `run-backtest`. The backtest dataset builder is already implemented in Python (`transforms.target_labels.build_backtest_dataset`) but is not yet wired as a dedicated CLI subcommand in `cli.py`, so the release workflow below uses the shipped library entry point for that step.

Important constraints before running the full pipeline:

- you need at least **272 trading days of upstream history** for the first non-empty Gold output
- the repository's checked-in fixtures are **smoke-size only** and do not contain enough history for a full non-empty Gold/backtest run
- therefore, the sequence below is a **command template** for a full run once you have sufficient Bronze coverage from expanded fixtures or a future live-ingest implementation

```bash
# 1) Bronze ingest the six datasets required by `build-features --layer all`
uv run --python 3.12 kospi-pipeline ingest \
  --source krx \
  --dataset kospi_index \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --source krx \
  --dataset investor_flow \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --source krx \
  --dataset market_valuation \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --source ecos \
  --dataset base_rate \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --source ecos \
  --dataset usd_krw \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --source ecos \
  --dataset bond_yield \
  --from 2023-01-01 \
  --to 2025-03-31 \
  --out data/bronze

# 2) Silver + Gold features
uv run --python 3.12 kospi-pipeline build-features \
  --layer all \
  --from 2024-01-02 \
  --to 2025-03-31 \
  --bronze-dir data/bronze \
  --silver-dir data/silver \
  --out data/gold

# 3) Backtest dataset materialization (shipped transform API)
uv run --python 3.12 python -c "from pathlib import Path; from kospi_decision_pipeline_app_kr_kospi.transforms.target_labels import build_backtest_dataset; build_backtest_dataset(Path('data/gold/decision_features.parquet'), Path('data/gold/backtest_dataset.parquet'))"

# 4) Scenario execution
uv run --python 3.12 kospi-pipeline run-scenario \
  --date 2025-04-01 \
  --scenario apps/kr-kospi/config/scenario.kospi.next_day.yaml \
  --features data/gold/decision_features.parquet \
  --out data/decisions

# 5) Walk-forward backtest
uv run --python 3.12 kospi-pipeline run-backtest \
  --dataset data/gold/backtest_dataset.parquet \
  --scenario apps/kr-kospi/config/scenario.kospi.next_day.yaml \
  --out data/backtests/v0_1
```

### Expected outputs

| Step | Output |
| --- | --- |
| Bronze ingest | `data/bronze/<source>/<dataset>/<date>.parquet` |
| Silver build | `data/silver/.../*.parquet` |
| Gold build | `data/gold/decision_features.parquet` |
| Backtest dataset build | `data/gold/backtest_dataset.parquet` |
| Scenario run | `data/decisions/kospi.next_day/<decision-date>.jsonl` |
| Backtest run | `data/backtests/v0_1/rows.jsonl`, `metrics.json`, `metrics.csv` |

## CLI reference

| Command | Status | Notes |
| --- | --- | --- |
| `ingest` | implemented | Bronze parquet ingestion |
| `build-features` | implemented | `silver`, `gold`, or `all` |
| `run-scenario` | implemented | ABDP scenario execution |
| `run-backtest` | implemented | Walk-forward reports |
| `build-backtest-dataset` | not yet exposed as CLI | Use `build_backtest_dataset(...)` from Python for v0.1 |

## Configuration reference

### `apps/kr-kospi/config/agents.yaml`

`agents.yaml` pins aggregate voting weights, final decision thresholds, and per-agent rule-version threshold maps.

| Block | Purpose |
| --- | --- |
| `weights` | DecisionAgent aggregation weights for `technical`, `domestic_macro`, `flow`, `valuation`, `volatility` |
| `thresholds.up` / `thresholds.down` | Final aggregate cutoffs for `up` and `down` |
| `agents.<name>.rule_version` | Exact binding rule contract version |
| `agents.<name>.thresholds` | Rule-specific thresholds validated against the rule version |

### `apps/kr-kospi/config/scenario.kospi.next_day.yaml`

The scenario file defines the runtime envelope used by `run-scenario` and `run-backtest`.

| Key | Current committed value | Meaning |
| --- | --- | --- |
| `scenario_id` | `kospi.next_day` | Scenario namespace for decision artifacts |
| `horizon` | `next_day` | Fixed v0.1 horizon |
| `agents` | `technical`, `domestic_macro`, `flow`, `valuation`, `volatility`, `decision` | ABDP participant order |
| `runtime.agents_config_path` | `apps/kr-kospi/config/agents.yaml` | Agent config source |
| `runtime.features_path` | `data/gold/features.parquet` | Default runtime features path in committed YAML |
| `runtime.output_dir` | `data/decisions` | Decision artifact root |

For generated Gold features in the current codebase, pass `--features data/gold/decision_features.parquet` explicitly or update the runtime block locally before running.

## Project layout

```text
core/
  src/kospi_decision_pipeline_core/
apps/kr-kospi/
  config/
  src/kospi_decision_pipeline_app_kr_kospi/
  tests/
docs/
  adr/
  spec.md
data/
  bronze/        # generated
  silver/        # generated
  gold/          # generated
  decisions/     # generated
  backtests/     # generated
```

## Testing

Run the default test suite:

```bash
uv run --python 3.12 --extra dev python -m pytest
```

Run with coverage gates matching CI:

```bash
uv run --python 3.12 --extra dev pytest \
  --cov=core/src \
  --cov=apps/kr-kospi/src \
  --cov-branch \
  --cov-report=xml \
  --cov-fail-under=100
```

Lint and typing checks:

```bash
uv run --python 3.12 --extra dev ruff check .
uv run --python 3.12 --extra dev ruff format --check .
uv run --python 3.12 --extra dev python scripts/check_typing_policy.py
uv run --python 3.12 --extra dev mypy --strict core/src apps/kr-kospi/src
```

## Public data attribution

- **KRX**: Korea Exchange market data and valuation inputs
- **ECOS**: Bank of Korea Economic Statistics System macro series
- **KOSIS**: supported public statistical connector surface in the data layer; not part of the current Gold/runtime path
- **Public Data Portal**: optional connector surface declared in the CLI and connector layer

## License

Licensed under the [Apache License 2.0](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for Oracle review workflow, branch naming, TDD expectations, coverage policy, and squash-merge rules.

## Design contract

The normative release contract lives in [docs/spec.md](docs/spec.md). ADR context begins with [docs/adr/001-project-foundation.md](docs/adr/001-project-foundation.md).

## ABDP attribution

This project depends on the Agent-Based Decision Pipeline reference implementation:

- Repository: <https://github.com/yeongseon/agent-based-decision-pipeline>
- Pinned SHA: `9520cfed7e150f644fb5d01bb1a9b32eb0082f8d`
