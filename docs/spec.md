# KOSPI Decision Pipeline Specification

## §1. Purpose

This specification defines the binding v0.1 contract for a public-data-first, deterministic KOSPI next-day direction pipeline built on ABDP. It is the normative reference for repository scope, schemas, rule logic, runtime orchestration, and release documentation.

## §2. Intended use

The project is for research, education, auditability, and reproducible experimentation. It is not a production trading system.

## §3. Output domain

- Model outputs: `up | down | skip`
- Backtest-only ground truth: `up | down | flat`

## §4. Data principle

v0.1 is public-data-first and Korea-focused. All shipped pipelines are built around public Korean data sources and deterministic transformations.

## §5. System summary

The system has two planes:

1. Data plane: Bronze → Silver → Gold parquet datasets
2. Decision plane: five rule agents + one DecisionAgent executed through ABDP `ScenarioRunner`

## §6. Supported public data sources

- KRX
- ECOS (Bank of Korea)
- KOSIS (Statistics Korea) connector surface for future or upstream expansion
- Public Data Portal connectors declared in code, where applicable

## §7. Repository topology

- `core/`: shared schemas, config loaders, runtime, backtest, serialization
- `apps/kr-kospi/`: KOSPI application package, CLI, transforms, fixtures, app tests
- `docs/`: ADRs and normative spec

## §8. Runtime baseline

- Python `>=3.12`
- `uv` is the preferred local dependency manager
- Repository package version at v0.1 release cut remains `0.0.1`

## §9. Determinism and reproducibility

- Parquet artifacts are the system-of-record interfaces between stages.
- Rule outputs are fixed-label, fixed-score branches.
- Decision outputs persist config signatures and snapshot identifiers.
- Runtime and backtest flows must be repeatable from the same inputs.

## §10. Explicit v0.1 exclusions

The following are out of scope for v0.1:

- S&P 500
- Nasdaq
- Dow
- VIX
- US futures
- real-time FX
- news sentiment
- broker reports
- individual stocks
- production trading automation

## §11. Bronze ingest contract

Bronze ingestion writes raw source snapshots to parquet under a source and dataset keyed directory structure. The shipped CLI surface for Bronze is `kospi-pipeline ingest`.

## §12. Silver normalization contract

Silver datasets are typed, normalized, source-aware parquet outputs derived from Bronze. Silver is the canonical typed staging layer used by Gold builders.

## §13. Gold feature contract

The shipped Gold feature builder writes `data/gold/decision_features.parquet`. Gold features must not contain `target_*` or `future_*` columns and must remain safe for direct agent scoring.

## §14. Leakage guardrails

- No agent may read `target_*` or `future_*` columns.
- No future-incorporating joins are allowed.
- Runtime feature rows must be strictly earlier than the decision date.
- Full-period normalization and hidden future leakage are forbidden.

## §15. Config contract

Scenario runtime config and agent config are YAML-driven and validated by strict loaders. Unknown agent IDs, mismatched rule versions, and missing threshold keys must raise validation errors.

## §16. Decision schema contract

Decision runtime outputs must preserve typed votes, final decision labels, aggregate score, snapshot identity, and config signature. Frozen decision schemas and deterministic serializers are part of the v0.1 contract.

## §17. Serialization and artifact contract

- Scenario decisions persist as JSONL under `data/decisions/<scenario_id>/<decision_date>.jsonl`
- Backtests persist `rows.jsonl`, `metrics.json`, and `metrics.csv`
- JSON serialization is deterministic and explicit

## §18. CLI surface contract

The shipped CLI currently implements:

- `ingest`
- `build-features`
- `run-scenario`
- `run-backtest`

`build_backtest_dataset(...)` is shipped as a Python API in `transforms.target_labels`, but a dedicated `build-backtest-dataset` CLI subcommand is not yet exposed in `cli.py` as of v0.1 release documentation finalization.

## §19-§23 Common execution contract

The following rules are binding for `technical@1.0.0`, `domestic_macro@1.0.0`, `flow@1.0.0`, `valuation@1.0.0`, and `volatility@1.0.0`.

- `row` means the current `AgentFeatureRow`.
- Branches are evaluated top-to-bottom. The first matching branch wins.
- Each branch emits a **fixed** `label` and **fixed** `score`. Scores are not interpolated from distance-to-threshold.
- `label=up` MUST have `score > 0`; `label=down` MUST have `score < 0`; `label=skip` MUST have `score = 0.0`.
- If any feature referenced by a branch is `null`, `NaN`, or non-finite, that branch is treated as **not matched**.
- If no non-fallback branch matches, the agent MUST emit the fallback branch: `label=skip`, `score=0.0`.
- Each agent MUST read **only** its declared whitelist. Any attempted access outside the whitelist MUST raise an input-validation error.
- Numeric conventions:
  - returns and percentiles use decimal form (`0.010 = 1.0%`)
  - `bok_base_rate_change_30d` and `kr_bond_yield_change_30d` use absolute percentage points (`0.25 = 25bp`)
  - `kospi_atr_14d` uses KOSPI index points
- The truth tables below are normative RED-test fixtures. Implementations MUST produce the stated branch, `label`, and `score`.

## §19. TechnicalAgent

**rule_version:** `technical@1.0.0`

**Inputs whitelist (and only these):**
- `kospi_return_1d`
- `kospi_return_5d`
- `kospi_ma5_gap`
- `kospi_close_position`

**Ordered rule logic**

1. **Bullish short-term trend continuation**
   - Predicate:
     - `row.kospi_ma5_gap >= agents.technical.thresholds.ma5_gap_up_min` (`0.005`)
     - `row.kospi_close_position >= agents.technical.thresholds.close_position_up_min` (`0.60`)
     - `row.kospi_return_5d >= agents.technical.thresholds.return_5d_up_min` (`0.010`)
   - Emit:
     - `label: up`
     - `score: 0.70`
   - Evidence:
     - `{ name: "kospi_ma5_gap", value: row.kospi_ma5_gap, source: "computed" }`
     - `{ name: "kospi_close_position", value: row.kospi_close_position, source: "computed" }`
     - `{ name: "kospi_return_5d", value: row.kospi_return_5d, source: "computed" }`
     - `{ name: "kospi_return_1d", value: row.kospi_return_1d, source: "computed" }`

2. **Bearish short-term trend continuation**
   - Predicate:
     - `row.kospi_ma5_gap <= agents.technical.thresholds.ma5_gap_down_max` (`-0.005`)
     - `row.kospi_close_position <= agents.technical.thresholds.close_position_down_max` (`0.40`)
     - `row.kospi_return_5d <= agents.technical.thresholds.return_5d_down_max` (`-0.010`)
   - Emit:
     - `label: down`
     - `score: -0.70`
   - Evidence:
     - `{ name: "kospi_ma5_gap", value: row.kospi_ma5_gap, source: "computed" }`
     - `{ name: "kospi_close_position", value: row.kospi_close_position, source: "computed" }`
     - `{ name: "kospi_return_5d", value: row.kospi_return_5d, source: "computed" }`
     - `{ name: "kospi_return_1d", value: row.kospi_return_1d, source: "computed" }`

3. **Mixed momentum abstain**
   - Predicate:
     - `(row.kospi_return_1d > 0.0 AND row.kospi_return_5d < 0.0) OR (row.kospi_return_1d < 0.0 AND row.kospi_return_5d > 0.0)`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_ma5_gap", value: row.kospi_ma5_gap, source: "computed" }`
     - `{ name: "kospi_close_position", value: row.kospi_close_position, source: "computed" }`
     - `{ name: "kospi_return_5d", value: row.kospi_return_5d, source: "computed" }`
     - `{ name: "kospi_return_1d", value: row.kospi_return_1d, source: "computed" }`

4. **Fallback**
   - Predicate: `else`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_ma5_gap", value: row.kospi_ma5_gap, source: "computed" }`
     - `{ name: "kospi_close_position", value: row.kospi_close_position, source: "computed" }`
     - `{ name: "kospi_return_5d", value: row.kospi_return_5d, source: "computed" }`
     - `{ name: "kospi_return_1d", value: row.kospi_return_1d, source: "computed" }`

**Threshold rationale:** use coarse trend filters only. A 0.5% MA gap and 1.0% 5-day move are large enough to filter routine daily noise without being curve-fit.

**Truth table**

| Row | kospi_return_1d | kospi_return_5d | kospi_ma5_gap | kospi_close_position | Expected branch | label | score |
|---|---:|---:|---:|---:|---|---|---:|
| T1 | 0.004 | 0.018 | 0.008 | 0.72 | Bullish short-term trend continuation | up | 0.70 |
| T2 | -0.006 | -0.015 | -0.009 | 0.28 | Bearish short-term trend continuation | down | -0.70 |
| T3 | 0.007 | -0.008 | 0.001 | 0.55 | Mixed momentum abstain | skip | 0.0 |
| T4 | 0.002 | 0.006 | 0.002 | 0.54 | Fallback | skip | 0.0 |



## §20. DomesticMacroAgent

**rule_version:** `domestic_macro@1.0.0`

**Inputs whitelist (and only these):**
- `bok_base_rate_change_30d`
- `usd_krw_return_5d`
- `kr_bond_yield_change_30d`

**Ordered rule logic**

1. **Supportive domestic macro**
   - Predicate:
     - `row.bok_base_rate_change_30d <= agents.domestic_macro.thresholds.bok_rate_change_up_max` (`0.00`)
     - `row.usd_krw_return_5d <= agents.domestic_macro.thresholds.usdkrw_return_5d_up_max` (`0.010`)
     - `row.kr_bond_yield_change_30d <= agents.domestic_macro.thresholds.bond_yield_change_30d_up_max` (`0.05`)
   - Emit:
     - `label: up`
     - `score: 0.60`
   - Evidence:
     - `{ name: "bok_base_rate_change_30d", value: row.bok_base_rate_change_30d, source: "computed" }`
     - `{ name: "usd_krw_return_5d", value: row.usd_krw_return_5d, source: "computed" }`
     - `{ name: "kr_bond_yield_change_30d", value: row.kr_bond_yield_change_30d, source: "computed" }`

2. **Risk-off domestic macro**
   - Predicate:
     - `row.bok_base_rate_change_30d >= agents.domestic_macro.thresholds.bok_rate_change_down_min` (`0.25`)  
       **OR**
     - `(row.usd_krw_return_5d >= agents.domestic_macro.thresholds.usdkrw_return_5d_down_min` (`0.020`)  
       `AND row.kr_bond_yield_change_30d >= agents.domestic_macro.thresholds.bond_yield_change_30d_down_min` (`0.10`))`
   - Emit:
     - `label: down`
     - `score: -0.70`
   - Evidence:
     - `{ name: "bok_base_rate_change_30d", value: row.bok_base_rate_change_30d, source: "computed" }`
     - `{ name: "usd_krw_return_5d", value: row.usd_krw_return_5d, source: "computed" }`
     - `{ name: "kr_bond_yield_change_30d", value: row.kr_bond_yield_change_30d, source: "computed" }`

3. **Conflicting macro signals abstain**
   - Predicate:
     - `(row.usd_krw_return_5d >= agents.domestic_macro.thresholds.usdkrw_return_5d_mixed_pos_min` (`0.015`) AND row.kr_bond_yield_change_30d < agents.domestic_macro.thresholds.bond_yield_change_30d_mixed_neg_max` (`0.00`))`  
       **OR**
     - `(row.usd_krw_return_5d <= agents.domestic_macro.thresholds.usdkrw_return_5d_mixed_neg_max` (`-0.015`) AND row.kr_bond_yield_change_30d > agents.domestic_macro.thresholds.bond_yield_change_30d_mixed_pos_min` (`0.05`))`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "bok_base_rate_change_30d", value: row.bok_base_rate_change_30d, source: "computed" }`
     - `{ name: "usd_krw_return_5d", value: row.usd_krw_return_5d, source: "computed" }`
     - `{ name: "kr_bond_yield_change_30d", value: row.kr_bond_yield_change_30d, source: "computed" }`

4. **Fallback**
   - Predicate: `else`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "bok_base_rate_change_30d", value: row.bok_base_rate_change_30d, source: "computed" }`
     - `{ name: "usd_krw_return_5d", value: row.usd_krw_return_5d, source: "computed" }`
     - `{ name: "kr_bond_yield_change_30d", value: row.kr_bond_yield_change_30d, source: "computed" }`

**Threshold rationale:** only large, macro-significant moves should matter on a one-day decision pipeline. A 25bp policy move and 1.5%-2.0% 5-day FX move are defensible “regime” thresholds rather than day-to-day noise.

**Truth table**

| Row | bok_base_rate_change_30d | usd_krw_return_5d | kr_bond_yield_change_30d | Expected branch | label | score |
|---|---:|---:|---:|---|---|---:|
| M1 | 0.00 | -0.004 | -0.02 | Supportive domestic macro | up | 0.60 |
| M2 | 0.25 | 0.005 | 0.01 | Risk-off domestic macro | down | -0.70 |
| M3 | 0.00 | 0.018 | -0.03 | Conflicting macro signals abstain | skip | 0.0 |
| M4 | 0.00 | 0.008 | 0.07 | Fallback | skip | 0.0 |

---

## §21. FlowAgent

**rule_version:** `flow@1.0.0`

**Inputs whitelist (and only these):**
- `foreign_net_buy_krw_5d_sum`
- `institution_net_buy_krw_5d_sum`
- `individual_net_buy_krw_5d_sum`
- `foreign_net_buy_5d_pct_of_turnover`

**Ordered rule logic**

1. **Aligned institutional demand**
   - Predicate:
     - `row.foreign_net_buy_krw_5d_sum > 0.0`
     - `row.institution_net_buy_krw_5d_sum >= 0.0`
     - `row.individual_net_buy_krw_5d_sum <= 0.0`
     - `row.foreign_net_buy_5d_pct_of_turnover >= agents.flow.thresholds.foreign_pct_up_min` (`0.010`)
   - Emit:
     - `label: up`
     - `score: 0.80`
   - Evidence:
     - `{ name: "foreign_net_buy_krw_5d_sum", value: row.foreign_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "institution_net_buy_krw_5d_sum", value: row.institution_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "individual_net_buy_krw_5d_sum", value: row.individual_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "foreign_net_buy_5d_pct_of_turnover", value: row.foreign_net_buy_5d_pct_of_turnover, source: "computed" }`

2. **Aligned institutional distribution**
   - Predicate:
     - `row.foreign_net_buy_krw_5d_sum < 0.0`
     - `row.institution_net_buy_krw_5d_sum <= 0.0`
     - `row.individual_net_buy_krw_5d_sum >= 0.0`
     - `row.foreign_net_buy_5d_pct_of_turnover <= agents.flow.thresholds.foreign_pct_down_max` (`-0.010`)
   - Emit:
     - `label: down`
     - `score: -0.80`
   - Evidence:
     - `{ name: "foreign_net_buy_krw_5d_sum", value: row.foreign_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "institution_net_buy_krw_5d_sum", value: row.institution_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "individual_net_buy_krw_5d_sum", value: row.individual_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "foreign_net_buy_5d_pct_of_turnover", value: row.foreign_net_buy_5d_pct_of_turnover, source: "computed" }`

3. **Divergent or weak flow abstain**
   - Predicate:
     - `(row.foreign_net_buy_krw_5d_sum * row.institution_net_buy_krw_5d_sum < 0.0)`  
       **OR**
     - `(abs(row.foreign_net_buy_5d_pct_of_turnover) < agents.flow.thresholds.foreign_pct_neutral_abs_max` (`0.003`))`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "foreign_net_buy_krw_5d_sum", value: row.foreign_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "institution_net_buy_krw_5d_sum", value: row.institution_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "individual_net_buy_krw_5d_sum", value: row.individual_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "foreign_net_buy_5d_pct_of_turnover", value: row.foreign_net_buy_5d_pct_of_turnover, source: "computed" }`

4. **Fallback**
   - Predicate: `else`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "foreign_net_buy_krw_5d_sum", value: row.foreign_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "institution_net_buy_krw_5d_sum", value: row.institution_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "individual_net_buy_krw_5d_sum", value: row.individual_net_buy_krw_5d_sum, source: "KRX" }`
     - `{ name: "foreign_net_buy_5d_pct_of_turnover", value: row.foreign_net_buy_5d_pct_of_turnover, source: "computed" }`

**Threshold rationale:** flow should be normalized by market activity, not raw KRW only. Using foreign flow as percent of turnover avoids regime drift, while requiring sign agreement with institutions avoids acting on single-cohort noise.

**Truth table**

| Row | foreign_net_buy_krw_5d_sum | institution_net_buy_krw_5d_sum | individual_net_buy_krw_5d_sum | foreign_net_buy_5d_pct_of_turnover | Expected branch | label | score |
|---|---:|---:|---:|---:|---|---|---:|
| F1 | 1200000000000 | 300000000000 | -1500000000000 | 0.012 | Aligned institutional demand | up | 0.80 |
| F2 | -1000000000000 | -200000000000 | 1200000000000 | -0.013 | Aligned institutional distribution | down | -0.80 |
| F3 | 500000000000 | -100000000000 | -400000000000 | 0.006 | Divergent or weak flow abstain | skip | 0.0 |
| F4 | 400000000000 | 100000000000 | -500000000000 | 0.005 | Fallback | skip | 0.0 |

---

## §22. ValuationAgent

**rule_version:** `valuation@1.0.0`

**Inputs whitelist (and only these):**
- `kospi_per`
- `kospi_pbr`
- `kospi_per_percentile_252d`
- `kospi_pbr_percentile_252d`

**Ordered rule logic**

1. **Relatively cheap market**
   - Predicate:
     - `row.kospi_per > 0.0`
     - `row.kospi_pbr > 0.0`
     - `row.kospi_per_percentile_252d <= agents.valuation.thresholds.per_percentile_up_max` (`0.30`)
     - `row.kospi_pbr_percentile_252d <= agents.valuation.thresholds.pbr_percentile_up_max` (`0.30`)
   - Emit:
     - `label: up`
     - `score: 0.55`
   - Evidence:
     - `{ name: "kospi_per", value: row.kospi_per, source: "KRX" }`
     - `{ name: "kospi_pbr", value: row.kospi_pbr, source: "KRX" }`
     - `{ name: "kospi_per_percentile_252d", value: row.kospi_per_percentile_252d, source: "computed" }`
     - `{ name: "kospi_pbr_percentile_252d", value: row.kospi_pbr_percentile_252d, source: "computed" }`

2. **Relatively expensive market**
   - Predicate:
     - `row.kospi_per > 0.0`
     - `row.kospi_pbr > 0.0`
     - `row.kospi_per_percentile_252d >= agents.valuation.thresholds.per_percentile_down_min` (`0.70`)
     - `row.kospi_pbr_percentile_252d >= agents.valuation.thresholds.pbr_percentile_down_min` (`0.70`)
   - Emit:
     - `label: down`
     - `score: -0.55`
   - Evidence:
     - `{ name: "kospi_per", value: row.kospi_per, source: "KRX" }`
     - `{ name: "kospi_pbr", value: row.kospi_pbr, source: "KRX" }`
     - `{ name: "kospi_per_percentile_252d", value: row.kospi_per_percentile_252d, source: "computed" }`
     - `{ name: "kospi_pbr_percentile_252d", value: row.kospi_pbr_percentile_252d, source: "computed" }`

3. **Fair-value band abstain**
   - Predicate:
     - `abs(row.kospi_per_percentile_252d - agents.valuation.thresholds.fair_value_center)` (`0.50`) `<= agents.valuation.thresholds.fair_value_half_band` (`0.10`)
     - `abs(row.kospi_pbr_percentile_252d - agents.valuation.thresholds.fair_value_center)` (`0.50`) `<= agents.valuation.thresholds.fair_value_half_band` (`0.10`)
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_per", value: row.kospi_per, source: "KRX" }`
     - `{ name: "kospi_pbr", value: row.kospi_pbr, source: "KRX" }`
     - `{ name: "kospi_per_percentile_252d", value: row.kospi_per_percentile_252d, source: "computed" }`
     - `{ name: "kospi_pbr_percentile_252d", value: row.kospi_pbr_percentile_252d, source: "computed" }`

4. **Fallback**
   - Predicate: `else`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_per", value: row.kospi_per, source: "KRX" }`
     - `{ name: "kospi_pbr", value: row.kospi_pbr, source: "KRX" }`
     - `{ name: "kospi_per_percentile_252d", value: row.kospi_per_percentile_252d, source: "computed" }`
     - `{ name: "kospi_pbr_percentile_252d", value: row.kospi_pbr_percentile_252d, source: "computed" }`

**Threshold rationale:** valuation should be relative, not anchored to fixed long-history constants. The 30th/70th percentile bands are broad enough to identify cheap/rich regimes without pretending valuation alone predicts each next day.

**Truth table**

| Row | kospi_per | kospi_pbr | kospi_per_percentile_252d | kospi_pbr_percentile_252d | Expected branch | label | score |
|---|---:|---:|---:|---:|---|---|---:|
| V1 | 9.8 | 0.86 | 0.18 | 0.22 | Relatively cheap market | up | 0.55 |
| V2 | 13.8 | 1.18 | 0.82 | 0.76 | Relatively expensive market | down | -0.55 |
| V3 | 11.5 | 0.98 | 0.54 | 0.47 | Fair-value band abstain | skip | 0.0 |
| V4 | 10.9 | 1.05 | 0.20 | 0.65 | Fallback | skip | 0.0 |

---

## §23. VolatilityAgent

**rule_version:** `volatility@1.0.0`

**Inputs whitelist (and only these):**
- `kospi_realized_vol_20d`
- `kospi_realized_vol_20d_percentile_252d`
- `kospi_atr_14d`

**Ordered rule logic**

1. **Calm regime support**
   - Predicate:
     - `row.kospi_realized_vol_20d <= agents.volatility.thresholds.realized_vol_20d_up_max` (`0.18`)
     - `row.kospi_realized_vol_20d_percentile_252d <= agents.volatility.thresholds.realized_vol_pct_up_max` (`0.30`)
     - `row.kospi_atr_14d <= agents.volatility.thresholds.atr_14d_up_max` (`35.0`)
   - Emit:
     - `label: up`
     - `score: 0.40`
   - Evidence:
     - `{ name: "kospi_realized_vol_20d", value: row.kospi_realized_vol_20d, source: "computed" }`
     - `{ name: "kospi_realized_vol_20d_percentile_252d", value: row.kospi_realized_vol_20d_percentile_252d, source: "computed" }`
     - `{ name: "kospi_atr_14d", value: row.kospi_atr_14d, source: "computed" }`

2. **Stress regime risk-off**
   - Predicate:
     - `row.kospi_realized_vol_20d_percentile_252d >= agents.volatility.thresholds.realized_vol_pct_down_min` (`0.80`)
     - `(row.kospi_realized_vol_20d >= agents.volatility.thresholds.realized_vol_20d_down_min` (`0.25`) `OR row.kospi_atr_14d >= agents.volatility.thresholds.atr_14d_down_min` (`45.0`))`
   - Emit:
     - `label: down`
     - `score: -0.65`
   - Evidence:
     - `{ name: "kospi_realized_vol_20d", value: row.kospi_realized_vol_20d, source: "computed" }`
     - `{ name: "kospi_realized_vol_20d_percentile_252d", value: row.kospi_realized_vol_20d_percentile_252d, source: "computed" }`
     - `{ name: "kospi_atr_14d", value: row.kospi_atr_14d, source: "computed" }`

3. **Middle-volatility abstain**
   - Predicate:
     - `row.kospi_realized_vol_20d_percentile_252d > agents.volatility.thresholds.realized_vol_pct_mid_low` (`0.30`)
     - `row.kospi_realized_vol_20d_percentile_252d < agents.volatility.thresholds.realized_vol_pct_mid_high` (`0.80`)
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_realized_vol_20d", value: row.kospi_realized_vol_20d, source: "computed" }`
     - `{ name: "kospi_realized_vol_20d_percentile_252d", value: row.kospi_realized_vol_20d_percentile_252d, source: "computed" }`
     - `{ name: "kospi_atr_14d", value: row.kospi_atr_14d, source: "computed" }`

4. **Fallback**
   - Predicate: `else`
   - Emit:
     - `label: skip`
     - `score: 0.0`
   - Evidence:
     - `{ name: "kospi_realized_vol_20d", value: row.kospi_realized_vol_20d, source: "computed" }`
     - `{ name: "kospi_realized_vol_20d_percentile_252d", value: row.kospi_realized_vol_20d_percentile_252d, source: "computed" }`
     - `{ name: "kospi_atr_14d", value: row.kospi_atr_14d, source: "computed" }`

**Threshold rationale:** volatility is primarily a risk throttle. Low volatility only adds a modest positive score; high volatility gets a stronger negative score because regime stress matters more than calmness for next-day decisioning.

**Truth table**

| Row | kospi_realized_vol_20d | kospi_realized_vol_20d_percentile_252d | kospi_atr_14d | Expected branch | label | score |
|---|---:|---:|---:|---|---|---:|
| O1 | 0.15 | 0.22 | 28.0 | Calm regime support | up | 0.40 |
| O2 | 0.29 | 0.88 | 47.0 | Stress regime risk-off | down | -0.65 |
| O3 | 0.21 | 0.55 | 34.0 | Middle-volatility abstain | skip | 0.0 |
| O4 | 0.20 | 0.85 | 30.0 | Fallback | skip | 0.0 |

---

## §24. Target labels and walk-forward backtest contract

### §24.1 Ground-truth target label

Ground truth is defined on the **next trading day close-to-close** move.

Let:

- `target_next_day_simple_return = (kospi_close[t+1] / kospi_close[t]) - 1.0`
- `target_next_day_log_return = ln(kospi_close[t+1] / kospi_close[t])`

Let the flat band be:

- `flat_band_abs_log_return = 0.001`

Then:

- if `target_next_day_log_return >= 0.001`, `target_direction_label = "up"`
- else if `target_next_day_log_return <= -0.001`, `target_direction_label = "down"`
- else, `target_direction_label = "flat"`

This label is for backtest/evaluation only. Agents MUST NOT read it.

### §24.2 Target column names

The following are the only target columns for v0.1, and all MUST use the `target_` prefix:

- `target_next_day_simple_return`
- `target_next_day_log_return`
- `target_direction_label`

Rules:

- No agent may read any column whose name matches `^target_`.
- No agent may read any column whose name matches `^future_`.
- `target_*` columns MUST exist only in `data/gold/backtest_dataset.parquet`.
- Gold feature datasets consumed by agents MUST NOT contain any `target_*` or `future_*` columns.

### §24.3 Walk-forward split

Walk-forward mode is fixed to **expanding-window** for v0.1. Rolling-window mode is out of scope.

Binding defaults:

- `min_train_rows = 252`
- `test_fold_size = 20` trading days
- `gap_days = 0`

Semantics:

1. Sort rows by `trade_date` ascending.
2. `train_cutoff` is the **inclusive** maximum `trade_date` in the train fold.
3. Fold 1:
   - train = first `252` eligible rows
   - test = next `20` eligible rows with `trade_date > train_cutoff`
4. Fold `k+1`:
   - expand train to include all prior train and prior test rows
   - set new `train_cutoff` to the last `trade_date` of the expanded train
   - test = next `20` eligible rows with `trade_date > train_cutoff`
5. The final fold MAY contain fewer than `20` rows. It MUST still be emitted if it contains at least `1` row.
6. Because `gap_days = 0`, the first test row is the immediate next eligible trading row after `train_cutoff`.

Raise condition:

- If any candidate test row has `trade_date <= train_cutoff`, the splitter MUST raise.
- Recommended exception text: `ValueError("test row date must be strictly greater than train_cutoff")`

Eligibility:

- A row is eligible only if all Gold feature columns required by the backtest job are non-null and all three target columns are non-null.
- The final source row, which has no `t+1` close and therefore no targets, MUST be excluded.

### §24.4 Output schema: `data/gold/backtest_dataset.parquet`

This file is the join of Gold features at date `t` and target columns derived from date `t+1`. It is the **only** file in the project allowed to contain `target_*`.

**Required columns**
- `trade_date`
- All Gold feature columns, verbatim:
  - `kospi_close`
  - `kospi_return_1d`
  - `kospi_return_3d`
  - `kospi_return_5d`
  - `kospi_ma5`
  - `kospi_ma20`
  - `kospi_ma5_gap`
  - `kospi_close_position`
  - `bok_base_rate`
  - `bok_base_rate_change_30d`
  - `usd_krw_close`
  - `usd_krw_return_5d`
  - `kr_bond_yield_3y`
  - `kr_bond_yield_change_30d`
  - `foreign_net_buy_krw_5d_sum`
  - `institution_net_buy_krw_5d_sum`
  - `individual_net_buy_krw_5d_sum`
  - `foreign_net_buy_5d_pct_of_turnover`
  - `kospi_per`
  - `kospi_pbr`
  - `kospi_per_percentile_252d`
  - `kospi_pbr_percentile_252d`
  - `kospi_realized_vol_20d`
  - `kospi_realized_vol_20d_percentile_252d`
  - `kospi_atr_14d`
- Target columns:
  - `target_next_day_simple_return`
  - `target_next_day_log_return`
  - `target_direction_label`

**Required invariants**
- sorted ascending by `trade_date`
- one row per `trade_date`
- no duplicate `trade_date`
- no other `target_*` columns
- no `future_*` columns
- agent runtime MUST strip or reject all `target_*` columns before scoring

### §24.5 `agents.yaml` schema extension (binding)

The existing aggregate weights and aggregate thresholds remain unchanged. Add a new `agents` block to pin `rule_version` and provide per-agent rule thresholds.

Validation rules:

- `weights` and `agents` MUST contain the same agent names.
- `agents.<name>.rule_version` MUST exactly match the version in this spec.
- `agents.<name>.thresholds` MUST contain exactly the keys required by that agent version.
- Missing or unknown threshold keys MUST raise config validation error.

**Full YAML structure**

```yaml
weights:
  technical: 0.30
  domestic_macro: 0.20
  flow: 0.25
  valuation: 0.10
  volatility: 0.15

thresholds:
  up: 0.25
  down: -0.25

agents:
  technical:
    rule_version: technical@1.0.0
    thresholds:
      ma5_gap_up_min: 0.005
      close_position_up_min: 0.60
      return_5d_up_min: 0.010
      ma5_gap_down_max: -0.005
      close_position_down_max: 0.40
      return_5d_down_max: -0.010

  domestic_macro:
    rule_version: domestic_macro@1.0.0
    thresholds:
      bok_rate_change_up_max: 0.00
      usdkrw_return_5d_up_max: 0.010
      bond_yield_change_30d_up_max: 0.05
      bok_rate_change_down_min: 0.25
      usdkrw_return_5d_down_min: 0.020
      bond_yield_change_30d_down_min: 0.10
      usdkrw_return_5d_mixed_pos_min: 0.015
      usdkrw_return_5d_mixed_neg_max: -0.015
      bond_yield_change_30d_mixed_pos_min: 0.05
      bond_yield_change_30d_mixed_neg_max: 0.00

  flow:
    rule_version: flow@1.0.0
    thresholds:
      foreign_pct_up_min: 0.010
      foreign_pct_down_max: -0.010
      foreign_pct_neutral_abs_max: 0.003

  valuation:
    rule_version: valuation@1.0.0
    thresholds:
      per_percentile_up_max: 0.30
      pbr_percentile_up_max: 0.30
      per_percentile_down_min: 0.70
      pbr_percentile_down_min: 0.70
      fair_value_center: 0.50
      fair_value_half_band: 0.10

  volatility:
    rule_version: volatility@1.0.0
    thresholds:
      realized_vol_20d_up_max: 0.18
      realized_vol_pct_up_max: 0.30
      atr_14d_up_max: 35.0
      realized_vol_pct_down_min: 0.80
      realized_vol_20d_down_min: 0.25
      atr_14d_down_min: 45.0
      realized_vol_pct_mid_low: 0.30
      realized_vol_pct_mid_high: 0.80
```

---

## §25. DecisionAgent aggregation contract

DecisionAgent consumes exactly five rule-agent votes and aggregates them with configured weights from `agents.yaml`.

Binding rules:

- input agent set must be `technical`, `domestic_macro`, `flow`, `valuation`, `volatility`
- aggregate thresholds come from `thresholds.up` and `thresholds.down`
- output labels remain `up | down | skip`
- config signature must be persisted on the final decision result

## §26. Scenario configuration contract

The shipped scenario config declares:

- `scenario_id: kospi.next_day`
- `horizon: next_day`
- six agents in order: five rule agents plus `decision`
- runtime block with `agents_config_path`, `features_path`, and `output_dir`

## §27. Scenario execution lifecycle

ABDP runtime proceeds in two phases:

1. `vote`: exactly five unique `VoteProposal` values from rule agents
2. `decide`: exactly one `DecisionResultProposal` from DecisionAgent

Any other proposal shape or count is invalid and must raise.

## §28. Runtime service outputs

`run_kospi_scenario(...)` must:

1. load scenario config
2. resolve agent config and feature paths
3. load exactly one lag-safe feature row for the requested decision date
4. run ABDP `ScenarioRunner`
5. persist one JSONL decision artifact under `data/decisions/<scenario_id>/<decision_date>.jsonl` or the supplied output override

Documented v0.1 drift:

- committed `scenario.kospi.next_day.yaml` points `runtime.features_path` to `data/gold/features.parquet`
- shipped Gold builder writes `data/gold/decision_features.parquet`
- release docs must therefore instruct users to pass `--features data/gold/decision_features.parquet` explicitly unless they customize the YAML locally

## §29. Backtest reporting contract

Backtest output files are:

- `rows.jsonl`
- `metrics.json`
- `metrics.csv`

Metrics include fold-level and overall statistics such as hit rate, precision, recall, skip rate, and flat rate.

## §30. Quality gate contract

- CI runs tests, Ruff lint/format checks, typing policy, and mypy
- new code is expected to maintain 100% line and branch coverage
- doc-only changes do not need coverage expansion

## §31. ADR linkage

ADR-001 is the architectural foundation for this specification. If an implementation choice conflicts with ADR-001, ADR-001 and this spec govern until superseded by a later accepted ADR and spec revision.

## §32. Versioning policy

- repository package version is currently `0.0.1`
- release documentation is prepared for the v0.1 milestone
- rule versions are explicitly pinned, e.g. `technical@1.0.0`

## §33. Public data attribution contract

Release documentation must attribute KRX and ECOS as the primary shipped v0.1 decision inputs, while also acknowledging KOSIS as a supported public-data connector surface in the broader repository.

## §34. Secrets and live access boundary

Live ingestion may require API credentials, but secrets must never be committed to the repository. Documentation may reference the need for credentials without embedding them.

## §35. Scale boundary

v0.1 is optimized for deterministic research workflows, not for high-throughput low-latency production deployment.

## §36. Artifact traceability

Generated outputs should remain traceable by path, date, scenario ID, snapshot ID, and config signature wherever those concepts apply.

## §37. Compatibility statement

The release contract is defined against the current mainline implementation that merged issues #1 through #19.

## §38. Packaging statement

The project is packaged from a single top-level `pyproject.toml` that includes both the shared core package and the `apps/kr-kospi` app package. There are no separate workspace `pyproject.toml` files under `core/` or `apps/kr-kospi/` in the shipped repository.

## §39. Testing strategy

The repository uses unit, contract, and integration tests to protect schemas, transforms, runtime behavior, and backtest determinism.

## §40. Terminology

- Bronze: raw source snapshot layer
- Silver: typed normalized dataset layer
- Gold: final lag-safe decision feature layer
- Scenario run: one next-day ABDP decision execution
- Backtest row: one scored decision paired with ground truth

## §41. Documentation obligations

Release documentation must be explicit about scope, exclusions, disclaimers, CLI surface, and any known drift between configuration defaults and generated artifacts.

## §42. Research-use statement

All release-facing docs must describe the repository as research-grade and educational, not production-ready.

## §43. Public-data limitations

v0.1 intentionally favors auditability and narrow scope over predictive breadth. Missing non-public, real-time, and cross-market features are a deliberate design constraint, not an omission.

## §44. Extension boundary

Future releases may add new markets, signals, or deployment surfaces, but such changes are non-binding for v0.1 unless explicitly versioned in this specification.

## §45. ABDP dependency attribution

ABDP integration is a first-class architectural dependency. Release documentation must reference <https://github.com/yeongseon/agent-based-decision-pipeline> at pinned SHA `9520cfed7e150f644fb5d01bb1a9b32eb0082f8d`.

## §46. License

The repository is licensed under Apache-2.0 and release documentation must link to `LICENSE`.

## §47. Disclaimer

> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental tool for research and education only. It is not investment advice or financial advisory.

This disclaimer must appear prominently in release-facing documentation.

## §48. v0.1 implementation status

The table below maps major spec areas to the shipped issue and PR set merged before documentation finalization.

| Spec area | Summary | Issue / PR |
| --- | --- | --- |
| §1-§10 | foundation, scope, exclusions | #1 / PR #21, #2 / PR #22 |
| §11 | Bronze ingest | #6 / PR #26 |
| §12 | Silver normalization | #7 / PR #27 |
| §13-§14 | Gold features and leakage guardrails | #8 / PR #29, #9 / PR #30 |
| §15 | typed config loading | #4 / PR #25 |
| §16-§17 | frozen schemas and deterministic serialization | #10 / PR #28 |
| §18 | CLI surface | #6 / PR #26, #19 / PR #40, issue #20 release audit |
| §19-§23 | rule-agent contracts | #11 / PR #33, #12 / PR #37, #13 / PR #35, #14 / PR #34, #15 / PR #32 |
| §24 | targets and walk-forward dataset | #18 / PR #36 |
| §25 | DecisionAgent aggregation | #16 / PR #38 |
| §26-§28 | ABDP runtime integration and scenario service | #17 / PR #39 |
| §29 | backtest reports | #19 / PR #40 |
| §30 | CI and policy gates | #3 / PR #23 |
| §31 | ADR linkage | #1 / PR #21 |
| §33 | public data connectors | #5 / PR #24 |
| §47-§50 | release documentation finalization | #20 |

## §49. Known limitations and documented drift

- No dedicated `build-backtest-dataset` CLI subcommand is exposed yet, even though the transform implementation exists.
- The committed scenario YAML defaults `runtime.features_path` to `data/gold/features.parquet`, while the shipped Gold feature builder writes `data/gold/decision_features.parquet`.
- v0.1 remains Korea-only, next-day-only, and rule-based.
- v0.1 is not production-ready and should not be presented as such.

## §50. Release notes, version log, and v0.2 roadmap

### v0.1 release notes

v0.1 completes the initial milestone: foundation, public-data ingest, typed normalization, Gold features, leakage guardrails, five rule agents, weighted decision aggregation, ABDP runtime execution, walk-forward backtesting, and release-grade documentation.

### Version log

- `0.0.1`: initial packaged repository line used throughout the v0.1 buildout
- `v0.1` milestone: documentation-complete release state after issues #1-#20

### v0.2 roadmap

- expose backtest-dataset generation as a first-class CLI subcommand
- reconcile default scenario feature paths with generated Gold artifact names
- add richer release automation and artifact publishing
- evaluate carefully scoped extensions without violating the public-data-first and anti-leakage principles
