# kospi-decision-pipeline

Deterministic next-day KOSPI direction pipeline built from Korean public data.

> **Disclaimer**
>
> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental research and educational tool. It is not investment advice or financial advisory.

## Project status

Project status: v0.1 in development.

## Scope

- Public-data-first KOSPI direction decisions
- Deterministic Bronze → Silver → Gold pipeline
- ABDP-native scenario execution for rule-based agents

## Documentation

- Spec placeholder: [docs/spec.md](docs/spec.md)
- ADRs: [docs/adr/](docs/adr/)

## Repository layout

- `core/` for shared schemas, IDs, and I/O helpers
- `apps/kr-kospi/` for the Korea KOSPI application package
- `.github/workflows/` reserved for CI workflows finalized in issue #3

## Quickstart

```bash
pip install -e ".[dev]"
kospi-pipeline --help
python -m kospi_decision_pipeline_app_kr_kospi --help
```

See #20 for finalized docs.
