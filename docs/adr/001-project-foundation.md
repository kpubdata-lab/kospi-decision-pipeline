# ADR-001: Project Foundation and v0.1 Scope

## Status
Accepted

## Date
2026-04-26

## Context
`kospi-decision-pipeline` is a public, deterministic decision pipeline for next-day KOSPI direction built only from Korean public data. The project must remain auditable, reproducible, and explicit about its scope boundaries because financial-domain tools are especially vulnerable to hidden leakage, undocumented heuristics, and accidental scope creep.

The repository is being created as a new public Apache-2.0 project under `kpubdata-lab`. It should follow the organization's public-data-first convention and reuse established packaging/CI patterns where they reduce maintenance cost.

## Decision
We adopt the following project foundation for v0.1:

1. **Purpose**
   - Produce a deterministic next-day KOSPI directional decision from domestic public data.
   - The model output label set is **`up | down | skip` only**.

2. **Ground truth**
   - Ground-truth labels may use **`up | down | flat`** for backtesting only.
   - `flat` is not a model output in v0.1.

3. **Data principle**
   - The project is **public-data-first**.
   - v0.1 uses only domestic public data sources such as KRX, ECOS, KOSIS, and 공공데이터포털-derived inputs.

4. **Architecture**
   - Bronze → Silver → Gold deterministic data plane.
   - Rule-based multi-agent decision plane executed through ABDP `ScenarioRunner`.
   - Reporting and backtesting are downstream of the deterministic decision path.

5. **Future-leakage prevention**
   - Agent inputs must never include `target_*` columns.
   - No future-incorporating moving averages.
   - No full-period normalization.
   - No full-period threshold tuning.

6. **v0.1 exclusions**
   - No S&P 500
   - No Nasdaq
   - No Dow
   - No VIX
   - No US futures
   - No real-time FX
   - No news sentiment
   - No broker reports
   - No individual stocks

## Consequences

### Positive
- Clear public scope and low ambiguity for contributors.
- Easier auditability and reproducibility.
- Lower risk of accidental dependence on non-domestic or non-public signals.

### Negative
- v0.1 will be intentionally narrow and may skip many days.
- Some potentially predictive signals are deferred to later versions.

## Related
- `docs/spec.md`
- `apps/kr-kospi/config/agents.yaml`
- `apps/kr-kospi/config/scenario.kospi.next_day.yaml`
