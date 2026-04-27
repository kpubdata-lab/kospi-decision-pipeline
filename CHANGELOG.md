# Changelog

> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental tool for research and education only. It is not investment advice or financial advisory.

## v0.3.0

### Added

- Issue #64 / PR #69: ADR-014 documenting the final `kpubdata.Client` migration, sister-package rationale, and the v0.2 → v0.3 operator upgrade path

### Changed

- Issue #60 / PR #65: froze v0.2 parity fixtures to protect the connector normalization contract during the migration
- Issue #61 / PR #66: introduced the shared `client_factory` and standardized live auth on `KPUBDATA_*_API_KEY` environment variables
- Issue #62 / PR #67: migrated the ECOS and KOSIS live connectors to `kpubdata.Client`
- Issue #63 / PR #68: migrated the KRX live connector to the authless `kpubdata[krx]` provider surface
- Issue #64 / PR #69: removed the final legacy connector HTTP/secret shims, refreshed operator/release docs, and finalized the v0.3.0 release notes

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
