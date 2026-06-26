#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.eventlog_e2e_harness import all_passed, format_results_table, run_battery


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        run = run_battery(Path(tmp))
        print(format_results_table(run))
        return 0 if all_passed(run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
