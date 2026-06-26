from __future__ import annotations

from evaluation.eventlog_e2e_harness import format_results_table, run_battery


def test_eventlog_e2e_integration(tmp_path) -> None:
    run = run_battery(tmp_path)

    assert run.db_path.exists(), f"missing events.db at {run.db_path}"

    failures = [row for row in run.rows if not row.passed]
    assert not failures, format_results_table(run)
