#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "ops" / "fixtures" / "world_grounded"
RUNTIME = ROOT / "ops" / "serial_runtime" / "world_overhaul"
STATE_PATH = RUNTIME / "state.json"
LOG_PATH = RUNTIME / "activity.jsonl"
REPORT_PATH = RUNTIME / "dominant_failure_report.md"
PATCH_RESULT_PATH = RUNTIME / "last_patch_result.md"
EVAL_PATH = ROOT / "evaluation" / "ras" / "store_eval_frontier.json"
OLLAMA = "http://127.0.0.1:11434/api/generate"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _append_log(kind: str, detail: str, **extra: Any) -> None:
    payload = {"ts": int(time.time()), "kind": kind, "detail": detail, "extra": extra}
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_state(**fields: Any) -> None:
    _write_json(STATE_PATH, {"updated_unix": int(time.time()), **fields})


def _run(cmd: list[str], *, timeout: int = 7200, name: str) -> subprocess.CompletedProcess[str]:
    _append_log("task_start", name, command=cmd)
    _write_state(mode="running", task=name, command=cmd)
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    _append_log(
        "task_finish",
        name,
        returncode=result.returncode,
        stdout_tail=result.stdout[-2000:],
        stderr_tail=result.stderr[-2000:],
    )
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed with code {result.returncode}")
    return result


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _ollama(prompt: str, *, model: str = "gemma3:27b-it-qat", timeout: int = 180) -> str:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        OLLAMA,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(request, timeout=timeout)).get("response", "").strip()
    except Exception as exc:  # noqa: BLE001
        return f"OLLAMA_ERROR: {exc}"


def _summary(payload: Any) -> dict[str, Any]:
    """Return the scored metrics dict.

    The eval artifact nests its metrics under a ``summary`` key
    (``{"summary": {...}, "results": [...]}``). Read through to it so the
    improvement/gate checks see the real numbers instead of falling back to
    defaults — the latter silently makes every check false (chief fix
    2026-06-29: caused a spurious no_improvement halt while correct rose 6->7
    and would never detect gate_met).
    """
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return payload["summary"]
    return payload if isinstance(payload, dict) else {}


def _improved(before: dict[str, Any] | None, after: dict[str, Any]) -> bool:
    if before is None:
        return True
    a = _summary(after)
    b = _summary(before)
    if bool(a.get("gate_met")) and not bool(b.get("gate_met")):
        return True
    if int(a.get("correct", 0)) > int(b.get("correct", 0)):
        return True
    if float(a.get("halluc_pct", 100.0)) < float(b.get("halluc_pct", 100.0)):
        return True
    return False


def _build_dominant_failure_report(iteration: int) -> None:
    eval_payload = _load_json(EVAL_PATH, {})
    helper_payload = _load_json(FIXTURES / "helper_outputs.json", [])
    binder_payload = _load_json(FIXTURES / "binder_outputs.json", {})
    brain_payload = _load_json(FIXTURES / "brain_outputs.json", [])
    prompt = (
        "You are a ruthless local critic for the TRACE world-grounded overhaul.\n"
        "Use only the provided artifacts.\n"
        "Return Markdown with exactly four sections: Dominant failure, Why it dominates, "
        "What not to touch, Validation to rerun.\n\n"
        f"EVAL:\n{json.dumps(eval_payload, indent=2)}\n\n"
        f"HELPER_FIXTURES:\n{json.dumps(helper_payload[:6], indent=2)}\n\n"
        f"BINDER_FIXTURES:\n{json.dumps(binder_payload, indent=2)}\n\n"
        f"BRAIN_FIXTURES:\n{json.dumps(brain_payload, indent=2)}\n"
    )
    text = _ollama(prompt)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        f"# Dominant Failure Report\n\nIteration: {iteration}\n\n{text}\n",
        encoding="utf-8",
    )


def _run_fixture_lane() -> None:
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/build_world_grounded_fixtures.py"],
        name="WG01_fixture_manifest",
    )
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/validate_world_grounded_fixtures.py", "--stage", "manifest"],
        name="WG01_validate_manifest",
    )
    helper_store = FIXTURES / "helper_store.sqlite3"
    _run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "scripts/light_ingest.py",
            str(FIXTURES / "selected_frames"),
            "--store",
            str(helper_store),
            "--backend",
            "local",
            "--helper-mode",
            "multi_helper",
            "--fresh",
        ],
        name="WG02_helper_ingest_local",
    )
    _run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "scripts/export_world_store.py",
            "--store",
            str(helper_store),
            "--out",
            str(FIXTURES / "helper_outputs.json"),
            "--node-types",
            "observation",
        ],
        name="WG02_export_helper_outputs",
    )
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/validate_world_grounded_fixtures.py", "--stage", "helper"],
        name="WG02_validate_helper_outputs",
    )
    _run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "scripts/build_synthetic_world_store.py",
            "--fresh",
        ],
        name="WG03_build_synthetic_binder_store",
    )
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/validate_world_grounded_fixtures.py", "--stage", "binder"],
        name="WG03_validate_binder_outputs",
    )
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/run_world_brain_fixture.py"],
        name="WG04_run_brain_fixture",
    )
    _run(
        [str(ROOT / ".venv" / "bin" / "python"), "scripts/validate_world_grounded_fixtures.py", "--stage", "brain"],
        name="WG04_validate_brain_outputs",
    )
    _run(
        [
            str(ROOT / ".venv" / "bin" / "pytest"),
            "tests/unit/test_store.py",
            "tests/unit/test_sleep.py",
            "tests/unit/test_agent.py",
            "tests/unit/test_world_grounded_memory.py",
            "-q",
        ],
        timeout=1800,
        name="WG05_architecture_tests",
    )


def main() -> int:
    loop_cap = int(os.environ.get("TRACE_WORLD_OVERHAUL_MAX_LOOPS", "4"))
    _run_fixture_lane()

    previous_eval: dict[str, Any] | None = None
    for iteration in range(1, loop_cap + 1):
        _write_state(mode="loop", iteration=iteration, loop_cap=loop_cap, task="WG06_real_bedroom_eval")
        _run(
            [
                str(ROOT / "scripts" / "run_frontier_room_cycle.sh"),
                "data/phone_captures/bedroom_dense_353f",
                "data/phone_captures/bedroom_kf40",
                "data/trace_store_frontier.sqlite3",
                "evaluation/ras/store_eval_frontier.json",
            ],
            timeout=7200,
            name=f"WG06_real_bedroom_eval_iter_{iteration}",
        )
        eval_payload = _load_json(EVAL_PATH, {})
        if bool(_summary(eval_payload).get("gate_met")):
            _append_log("complete", "gate met", iteration=iteration, eval=eval_payload)
            _write_state(mode="complete", iteration=iteration, eval=eval_payload)
            return 0

        _build_dominant_failure_report(iteration)
        _append_log("report", "dominant failure report refreshed", iteration=iteration)

        _run(
            [str(ROOT / "scripts" / "run_codex_brief.sh"), "ops/serial_queue/world_overhaul/WG08_dominant_failure_patch.md"],
            timeout=7200,
            name=f"WG08_codex_patch_iter_{iteration}",
        )
        _run(
            [
                str(ROOT / ".venv" / "bin" / "pytest"),
                "tests/unit/test_store.py",
                "tests/unit/test_sleep.py",
                "tests/unit/test_agent.py",
                "tests/unit/test_world_grounded_memory.py",
                "-q",
            ],
            timeout=1800,
            name=f"WG09_retest_iter_{iteration}",
        )

        if not PATCH_RESULT_PATH.exists():
            _append_log("halt", "patch result note missing", iteration=iteration)
            _write_state(mode="halted", reason="patch_result_missing", iteration=iteration)
            return 1

        if previous_eval is not None and not _improved(previous_eval, eval_payload):
            _append_log("halt", "no eval improvement after latest patch cycle", iteration=iteration, eval=eval_payload)
            _write_state(mode="halted", reason="no_improvement", iteration=iteration, eval=eval_payload)
            return 1
        previous_eval = eval_payload

    _append_log("halt", "loop cap reached without gate", loop_cap=loop_cap)
    _write_state(mode="halted", reason="loop_cap_reached", loop_cap=loop_cap)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
