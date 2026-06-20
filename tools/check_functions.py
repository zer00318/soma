from __future__ import annotations

import ast
import sys
from pathlib import Path

MAX_LINES = 60
MAX_COMPLEXITY = 10


def complexity(node: ast.AST) -> int:
    branches = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler)
    boolean_branches = sum(
        max(0, len(child.values) - 1) for child in ast.walk(node) if isinstance(child, ast.BoolOp)
    )
    return 1 + sum(isinstance(child, branches) for child in ast.walk(node)) + boolean_branches


def violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = node.end_lineno or node.lineno
        length = end - node.lineno + 1
        if length > MAX_LINES:
            errors.append(f"{path}:{node.lineno}: {node.name} is {length} lines (max {MAX_LINES})")
        score = complexity(node)
        if score > MAX_COMPLEXITY:
            errors.append(
                f"{path}:{node.lineno}: {node.name} complexity is {score} (max {MAX_COMPLEXITY})"
            )
    return errors


def main() -> int:
    roots = [Path(arg) for arg in sys.argv[1:]] or [Path("src")]
    paths = (path for root in roots for path in root.rglob("*.py"))
    errors = [error for path in paths for error in violations(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
