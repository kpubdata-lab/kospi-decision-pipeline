# Contributing

> 본 프로젝트는 연구 및 교육 목적의 실험 도구이며, 투자 권유 또는 금융 자문이 아닙니다.
>
> This project is an experimental tool for research and education only. It is not investment advice or financial advisory.

## Toolchain

- Python 3.12+
- `uv`
- GitHub CLI (`gh`) for issue and PR workflows

Install development dependencies:

```bash
uv sync --extra dev
```

## Branch and PR conventions

- Branch name: `feat/issue-<N>-<slug>`
- PR title: `<verb-phrase> (#<N>)`
- Merge policy: **squash merge only**

Example:

- Branch: `feat/issue-20-docs-finalization`
- PR title: `Finalize v0.1 documentation: README, spec, CONTRIBUTING (#20)`

## Required delivery workflow

1. Start from an open GitHub issue.
2. Consult Oracle before or during implementation when the change is non-trivial.
3. Follow TDD: **RED → GREEN → REFACTOR (optional)**.
4. Keep the work atomic. Default expectation is **3 commits per issue**, each referencing the issue number. Doc-only changes may use fewer when the review stays atomic.
5. Run local verification before opening or updating the PR.
6. Request Oracle review again before merge.
7. Merge with **squash** after all blockers are cleared.

## Oracle review policy

- Consult Oracle before implementation for ambiguous or high-risk work.
- Merge target: **100/100**.
- Acceptable non-blocking pass threshold: **PASS with no blockers and at least 95/100**.
- Documentation-only work may accept a lower pass only when explicitly approved in the issue or release workflow.

Record any drift between spec, docs, and shipped code in the PR description.

These Oracle requirements are team workflow conventions for this repository; they are not enforced by the Python package itself.

## TDD expectations

- RED: write or update a failing test first whenever code behavior changes.
- GREEN: implement the smallest change that makes the test pass.
- REFACTOR: optional cleanup without behavior drift.
- Never merge code that reduces clarity around determinism, leakage prevention, or schema guarantees.

## Tests, lint, and typing

Run the baseline suite:

```bash
uv run --python 3.12 --extra dev python -m pytest
```

Run the CI-equivalent coverage command:

```bash
uv run --python 3.12 --extra dev pytest \
  --cov=core/src \
  --cov=apps/kr-kospi/src \
  --cov-branch \
  --cov-report=xml \
  --cov-fail-under=100
```

Run lint and typing:

```bash
uv run --python 3.12 --extra dev ruff check .
uv run --python 3.12 --extra dev ruff format --check .
uv run --python 3.12 --extra dev python scripts/check_typing_policy.py
uv run --python 3.12 --extra dev mypy --strict core/src apps/kr-kospi/src
```

## Coverage policy

- New code must maintain **100% line and branch coverage**.
- Doc-only changes do not require coverage expansion.
- Do not weaken coverage thresholds without an explicit issue and reviewer approval.

## Typing policy

- No `Any` without a written justification in code review.
- No `# type: ignore` without explicit reviewer approval and a comment explaining the boundary.
- Preserve `mypy --strict` compatibility.

## Commit guidance

- Reference the issue number in every commit message.
- Keep commits revertible and scoped to one concern.
- Prefer separate commits for docs, code, and fixtures when they can be reviewed independently.

## Filing issues

- Use the repository issue tracker: <https://github.com/kpubdata-lab/kospi-decision-pipeline/issues>
- If templates are later added under `.github/ISSUE_TEMPLATE/`, use the closest matching template.
- Include scope, expected behavior, non-goals, and verification notes.

## Project boundaries

Contributions for v0.1 must respect the documented exclusions:

- no S&P 500
- no real-time FX
- no broker reports
- no individual-stock prediction
- no production-readiness claims
