from __future__ import annotations

import argparse
import io
import tokenize
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import cast


DEFAULT_TARGETS = (
    Path("core/src"),
    Path("apps/kr-kospi/src"),
)


def iter_python_files(targets: Sequence[Path]) -> Iterable[Path]:
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            yield target
            continue
        if target.is_dir():
            yield from sorted(target.rglob("*.py"))


def has_allow_any_marker(line: str) -> bool:
    return "# allow-any:" in line


def find_violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    violations: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        if "# type: ignore" in line:
            violations.append(f"{path}:{line_number}: disallowed # type: ignore")

    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    seen_any_lines: set[int] = set()
    for token in tokens:
        if token.type != tokenize.NAME or token.string != "Any":
            continue
        if token.start[0] in seen_any_lines:
            continue
        seen_any_lines.add(token.start[0])
        line = lines[token.start[0] - 1]
        if has_allow_any_marker(line):
            continue
        violations.append(f"{path}:{token.start[0]}: bare Any requires inline allow-any marker")

    return violations


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("targets", nargs="*", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    targets = tuple(cast(list[Path], args.targets)) or DEFAULT_TARGETS

    violations: list[str] = []
    checked_files = 0
    for path in iter_python_files(targets):
        checked_files += 1
        violations.extend(find_violations(path))

    if violations:
        print("typing policy violations found:")
        for violation in violations:
            print(violation)
        return 1

    print(f"typing policy clean: checked {checked_files} Python files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
