# Changelog

> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental tool for research and education only. It is not investment advice or financial advisory.

## v0.1

### Foundation

- Issue #1 / PR #21: ADR-001 project foundation and v0.1 scope
- Issue #2 / PR #22: repository scaffold and Python packaging
- Issue #3 / PR #23: CI workflows and policy gates
- Issue #4 / PR #25: typed config loaders for scenario and agent configs
- Issue #5 / PR #24: public-data connector protocols and fixture clients

### Data plane

- Issue #6 / PR #26: Bronze ingest pipeline and ingest CLI
- Issue #7 / PR #27: Silver typed normalization
- Issue #8 / PR #29: Gold decision-feature dataset
- Issue #9 / PR #30: leakage guardrails and sanitized agent inputs
- Issue #18 / PR #36: target labels and walk-forward backtest dataset

### Decision and runtime

- Issue #10 / PR #28: frozen decision schemas and deterministic serializers
- Issue #11 / PR #33: TechnicalAgent rule logic
- Issue #12 / PR #37: DomesticMacroAgent rule logic
- Issue #13 / PR #35: FlowAgent rule logic
- Issue #14 / PR #34: ValuationAgent rule logic
- Issue #15 / PR #32: VolatilityAgent rule logic
- Issue #16 / PR #38: DecisionAgent weighted aggregation
- Issue #17 / PR #39: ABDP ScenarioRunner integration and runtime service

### Backtest

- Issue #19 / PR #40: walk-forward backtest runner and report writers

### Documentation

- Issue #20: release-ready README, spec, contributing guide, and changelog finalization
