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

- Release target: **v0.2**
- Project posture: **research-grade, deterministic, public-data-first**
- Out of scope for v0.2: S&P 500, real-time FX, broker reports, individual stocks, production trading automation
- KOSIS in v0.2: **bronze-only live ingest**; it is not part of the shipped Silver/Gold/runtime path unless a later cadence-normalization issue lands

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
- `KPUBDATA_BOK_API_KEY` for live ECOS ingest; `KPUBDATA_KOSIS_API_KEY` only if you want the optional bronze-only KOSIS live ingest in v0.2
- KRX live smoke does not require a repository secret, but the scheduled GitHub Actions workflow falls back to fixture smoke when required live secrets are absent

Environment variables typically used for live runs depend on the upstream data client configuration. For safe automation, export the non-interactive shell settings used in CI:

```bash
export CI=true DEBIAN_FRONTEND=noninteractive GIT_TERMINAL_PROMPT=0 \
  GCM_INTERACTIVE=never HOMEBREW_NO_AUTO_UPDATE=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1
```

Live-mode variables documented in `.env.example`:

```bash
KPUBDATA_BOK_API_KEY=
KPUBDATA_KOSIS_API_KEY=
KOSPI_PIPELINE_LIVE_ECOS=0
KOSPI_PIPELINE_LIVE_KRX=0
```

- `KPUBDATA_BOK_API_KEY` is required for live ECOS bronze ingest.
- `KPUBDATA_KOSIS_API_KEY` is optional and only used for bronze-only KOSIS ingest in v0.2.
- `KOSPI_PIPELINE_LIVE_ECOS=1` and `KOSPI_PIPELINE_LIVE_KRX=1` opt into the guarded live pytest smoke cases.

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
uv run --python 3.12 kospi-pipeline run --help
uv run --python 3.12 kospi-pipeline run-backtest --help
uv run --python 3.12 python -c "from kospi_decision_pipeline_app_kr_kospi.transforms.target_labels import build_backtest_dataset; print(build_backtest_dataset.__name__)"
```

### Live-mode snapshot example

The shipped CLI implements `ingest`, `build-features`, `run`, `run-scenario`, and `run-backtest`. The backtest dataset builder is already implemented in Python (`transforms.target_labels.build_backtest_dataset`) but is not yet wired as a dedicated CLI subcommand in `cli.py`, so the live-smoke workflow and local runbook use the shipped library entry point for that step.

Important constraints before running the full pipeline:

- you need at least **272 trading days of upstream history** for the first non-empty Gold output
- the repository's checked-in fixtures are **smoke-size only** and do not contain enough history for a full non-empty Gold/backtest run
- live runs are **snapshot-aware** and write under a snapshot root, so Silver/Gold should point at one chosen snapshot at a time
- reruns against the **same** live snapshot are idempotent and skip already-written Bronze partitions instead of rewriting them

```bash
export KPUBDATA_BOK_API_KEY="your-bok-key"
export KPUBDATA_KOSIS_API_KEY="your-kosis-key" # optional; KOSIS is bronze-only in v0.2
SNAPSHOT_ID="snapshot-$(date -u +%Y%m%dT%H%M%SZ)"
LIVE_FROM="2024-01-01"
LIVE_TO="2025-03-31"
```

```bash
# 1) Bronze ingest the six Silver/Gold inputs into one snapshot root
uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source krx \
  --dataset kospi_index \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source krx \
  --dataset investor_flow \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source krx \
  --dataset market_valuation \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source ecos \
  --dataset base_rate \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source ecos \
  --dataset usd_krw \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source ecos \
  --dataset bond_yield \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

# Optional bronze-only KOSIS ingest in v0.2. This does not feed Gold/runtime yet.
uv run --python 3.12 kospi-pipeline ingest \
  --live \
  --source kosis \
  --dataset macro_indicators \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --snapshot-id "$SNAPSHOT_ID" \
  --out data/bronze

# 2) Silver + Gold features from one snapshot-aware Bronze root
uv run --python 3.12 kospi-pipeline build-features \
  --layer all \
  --from "$LIVE_FROM" \
  --to "$LIVE_TO" \
  --bronze-dir "data/bronze/$SNAPSHOT_ID" \
  --silver-dir "data/silver/$SNAPSHOT_ID" \
  --out "data/gold/$SNAPSHOT_ID"

# 3) Backtest dataset materialization (shipped transform API)
uv run --python 3.12 python -c "import os; from pathlib import Path; from kospi_decision_pipeline_app_kr_kospi.transforms.target_labels import build_backtest_dataset; snapshot_id = os.environ['SNAPSHOT_ID']; build_backtest_dataset(Path(f'data/gold/{snapshot_id}/decision_features.parquet'), Path(f'data/gold/{snapshot_id}/backtest_dataset.parquet'))"

# 4) Snapshot decision execution
uv run --python 3.12 kospi-pipeline run \
  --scenario apps/kr-kospi/config/scenario.kospi.next_day.yaml \
  --features "data/gold/$SNAPSHOT_ID/decision_features.parquet" \
  --out "data/decisions/$SNAPSHOT_ID"

# 5) Walk-forward backtest
uv run --python 3.12 kospi-pipeline run-backtest \
  --dataset "data/gold/$SNAPSHOT_ID/backtest_dataset.parquet" \
  --scenario apps/kr-kospi/config/scenario.kospi.next_day.yaml \
  --out "data/backtests/$SNAPSHOT_ID"
```

### Snapshot-aware Bronze roots and reruns

- The snapshot-aware Bronze contract to reason about operationally is `data/bronze/<source>/<dataset>/<snapshot_id>/<date>.parquet`.
- The current CLI realizes that contract by selecting a snapshot-scoped Bronze root first, so with the default `--out data/bronze` the physical path is `data/bronze/<snapshot_id>/<source>/<dataset>/<date>.parquet` on disk while each manifest entry remains dataset-relative as `<source>/<dataset>/<date>.parquet`.
- Treat the snapshot directory as the immutable Bronze root for one run, then point `build-features --bronze-dir` at that exact snapshot path.
- Re-running the same live ingest command with the same `--snapshot-id` is idempotent: existing partitions are skipped, new missing dates are appended, and the manifest records `written_dates` vs `skipped_dates`.
- If you want a fresh replay, choose a new `snapshot-YYYYMMDDTHHMMSSZ` identifier instead of deleting old data in place.

### Nightly workflow and secret setup

- GitHub Actions workflow: `.github/workflows/live-smoke.yml`
- `KPUBDATA_BOK_API_KEY` is required for the full live path.
- `KPUBDATA_KOSIS_API_KEY` is optional and only enables the bronze-only KOSIS ingest path in v0.2.
- When `KPUBDATA_BOK_API_KEY` is missing, the workflow prints a warning and falls back to fixture-backed CLI smoke (`ingest`, `build-features`, `run`, `run-backtest`) instead of failing silently.
- When `KPUBDATA_KOSIS_API_KEY` is missing, the workflow still runs KRX + ECOS + Silver/Gold + runtime smoke and prints that KOSIS was skipped.
- The acceptance text may say `backtest` informally, but the shipped CLI command used by the workflow is `run-backtest`.
- Upstream auth failures, schema drift, and missing required inputs are intentionally loud because each workflow shell step runs with `set -euo pipefail` and explicit step headers.

### Expected outputs

| Step | Output |
| --- | --- |
| Bronze ingest | `data/bronze/<snapshot_id>/<source>/<dataset>/<date>.parquet` for live runs; `data/bronze/<source>/<dataset>/<date>.parquet` for fixture runs |
| Silver build | `data/silver/.../*.parquet` |
| Gold build | `data/gold/<snapshot_id>/decision_features.parquet` (or another chosen Gold root) |
| Backtest dataset build | `data/gold/<snapshot_id>/backtest_dataset.parquet` |
| Snapshot run | `data/decisions/<snapshot_id>/kospi.next_day/<decision-date>.jsonl` |
| Backtest run | `data/backtests/<snapshot_id>/rows.jsonl`, `metrics.json`, `metrics.csv` |

## CLI reference

| Command | Status | Notes |
| --- | --- | --- |
| `ingest` | implemented | Bronze parquet ingestion |
| `build-features` | implemented | `silver`, `gold`, or `all` |
| `run` | implemented | Run decisions over the latest Gold snapshot row |
| `run-scenario` | implemented | ABDP scenario execution |
| `run-backtest` | implemented | Walk-forward reports |
| `build-backtest-dataset` | not yet exposed as CLI | Use `build_backtest_dataset(...)` from Python for v0.2 |
| `backtest` | stubbed | Placeholder only; use `run-backtest` |

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
| `horizon` | `next_day` | Fixed v0.2 horizon |
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

## Operator runbook

- Daily/nightly operations, secret rotation, snapshot conventions, and schema-drift response steps live in [docs/operator.md](docs/operator.md).

## Design contract

The normative release contract lives in [docs/spec.md](docs/spec.md). That document still captures the binding v0.1 rules/runtime baseline; the v0.2 operator additions in this README and [docs/operator.md](docs/operator.md) layer on top without changing the published rule contracts. ADR context begins with [docs/adr/001-project-foundation.md](docs/adr/001-project-foundation.md).

## ABDP attribution

This project depends on the Agent-Based Decision Pipeline reference implementation:

- Repository: <https://github.com/yeongseon/agent-based-decision-pipeline>
- Pinned SHA: `9520cfed7e150f644fb5d01bb1a9b32eb0082f8d`
