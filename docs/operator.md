# Operator runbook

## Scope

This runbook covers the v0.2 operating path for nightly or ad-hoc live smoke runs.

- KRX + ECOS feed the shipped Silver/Gold/runtime path.
- KOSIS live ingest is **bronze-only in v0.2** and must not be treated as a Gold/runtime dependency unless a later cadence-normalization issue lands.
- Fixture smoke remains the fallback when required live secrets are absent.

## Daily / nightly run procedure

Primary automation lives in `.github/workflows/live-smoke.yml`.

1. Trigger path
   - scheduled daily at `0 18 * * *` UTC (`03:00` KST)
   - or `workflow_dispatch` for ad-hoc replay
2. Bootstrap
   - checkout
   - Python 3.12 setup
   - `uv sync --extra dev`
3. Live-mode decision tree
   - if `ECOS_API_KEY` is present, run live KRX + ECOS ingest
   - if `KOSIS_API_KEY` is also present, run optional bronze-only KOSIS ingest
   - if `ECOS_API_KEY` is absent, print a warning and fall back to fixture-backed CLI smoke
4. Materialization
   - build Silver/Gold from one chosen snapshot-aware Bronze root
   - run `kospi-pipeline run`
   - build a backtest dataset with `build_backtest_dataset(...)`
   - trim to a short recent window and run `kospi-pipeline run-backtest`

All workflow shell blocks run with `set -euo pipefail` and explicit headers so auth failures, schema drift, and missing required inputs fail loudly in the job log.

## Snapshot ID conventions

Use UTC timestamped snapshot IDs:

```text
snapshot-YYYYMMDDTHHMMSSZ
```

Example:

```text
snapshot-20260426T180000Z
```

Guidelines:

- one snapshot ID per ingest batch
- do not mix multiple live ingest waves into one snapshot unless you are intentionally resuming the same batch
- point downstream transforms at the exact snapshot root, for example `data/bronze/<snapshot_id>`
- keep snapshots immutable after success; create a new snapshot for a true rerun

Logical Bronze contract:

```text
data/bronze/<source>/<dataset>/<snapshot_id>/<date>.parquet
```

Current on-disk layout from the default Bronze output root:

```text
data/bronze/<snapshot_id>/<source>/<dataset>/<date>.parquet
```

## Rerun semantics

Live Bronze ingest is idempotent for the same `--snapshot-id`.

- existing partitions are skipped
- missing partitions for the requested date range are appended
- manifests record which dates were written, skipped, or failed

Operationally:

- use the same snapshot ID when you want a safe resume of an interrupted ingest
- use a new snapshot ID when you want an auditable fresh replay
- avoid mutating or deleting individual parquet partitions inside a completed snapshot unless you are handling an incident and recording that manual action elsewhere

## Secret setup and rotation

Repository / environment secrets:

- `ECOS_API_KEY` — required for full live smoke
- `KOSIS_API_KEY` — optional, bronze-only in v0.2

Rotation procedure:

1. generate the replacement key upstream
2. update the GitHub Actions secret in the target repository or environment
3. trigger `workflow_dispatch`
4. confirm live ingest passes with the new key
5. revoke the old key upstream once the smoke run is green

Local operators can mirror the same names in a private `.env` file, but `.env.example` must stay credential-free.

## Schema drift response

Typical symptoms:

- live ingest step fails with parsing or validation errors
- Silver normalization fails after Bronze ingest succeeded
- Gold build fails because expected columns are missing or renamed

Response checklist:

1. identify the failing step from the workflow header in the job log
2. capture the upstream source, dataset, date range, and snapshot ID
3. inspect the written Bronze snapshot and manifest to determine whether the break happened at fetch time or transform time
4. if the issue is auth-related, rotate / re-enter the secret and rerun
5. if the issue is schema-related, open a follow-up fix with the failing sample payload or parquet attached
6. do not silently patch around required-column loss in the workflow; the failure is expected to stay loud

## Manual ad-hoc commands

```bash
export ECOS_API_KEY="..."
export KOSIS_API_KEY="..." # optional
SNAPSHOT_ID="snapshot-$(date -u +%Y%m%dT%H%M%SZ)"

uv run --python 3.12 kospi-pipeline ingest --live --source krx --dataset kospi_index --from 2024-01-01 --to 2025-03-31 --snapshot-id "$SNAPSHOT_ID" --out data/bronze
uv run --python 3.12 kospi-pipeline ingest --live --source ecos --dataset base_rate --from 2024-01-01 --to 2025-03-31 --snapshot-id "$SNAPSHOT_ID" --api-key "$ECOS_API_KEY" --out data/bronze
uv run --python 3.12 kospi-pipeline build-features --layer all --from 2024-01-01 --to 2025-03-31 --bronze-dir "data/bronze/$SNAPSHOT_ID" --silver-dir "data/silver/$SNAPSHOT_ID" --out "data/gold/$SNAPSHOT_ID"
uv run --python 3.12 kospi-pipeline run --features "data/gold/$SNAPSHOT_ID/decision_features.parquet" --out "data/decisions/$SNAPSHOT_ID"
```
