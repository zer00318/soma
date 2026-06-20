#!/usr/bin/env bash
# Quality gate for the production core (src/soma + tests/unit). Ratchets quality
# on new code; the legacy garage (scripts/*, tests/test_*.py) is migrated behind
# this gate one strangler-fig PR at a time, never lowering the bar here.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || true

run() { echo "== $1 =="; shift; "$@"; }

run "ruff lint"          ruff check src tests/unit
run "ruff format check"  ruff format --check src tests/unit
run "mypy (strict)"      mypy src
run "pytest (unit)"      pytest -q
run "gold integrity"     python -m soma.eval.gold_lock verify
run "dead code"          vulture src --min-confidence 80

echo "ALL GREEN"
