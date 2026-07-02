#!/usr/bin/env python3
"""Conservative 24/7 local-LLM execution loop for the truthful prototype path.

The daemon does not invent new product work. It repeatedly:
1. runs the real unified-store eval,
2. reads the measured artifact,
3. asks local Ollama models for a bounded scout summary + critic next-step,
4. sleeps adaptively based on whether the store or result changed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "ops" / "serial_runtime"
STATE_PATH = RUNTIME / "state.json"
ACTIVITY_PATH = RUNTIME / "activity.jsonl"
CHECKPOINTS_PATH = RUNTIME / "checkpoints.json"
REPORTS_DIR = RUNTIME / "reports"

STORE_DB = ROOT / "data" / "trace_store.sqlite3"
GROUND_TRUTH = ROOT / "data" / "phone_captures" / "live" / "ground_truth.json"
STORE_EVAL = ROOT / "evaluation" / "ras" / "store_eval.json"
LIVE44 = ROOT / "evaluation" / "ras" / "live44_summary.json"

OLLAMA = "http://127.0.0.1:11434/api/generate"
SCOUT_MODEL = "gemma3:12b-it-qat"
CRITIC_MODEL = "gemma3:27b-it-qat"

SHORT_SLEEP_S = 600
LONG_SLEEP_S = 1800
WAIT_SLEEP_S = 30


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _append_activity(kind: str, detail: str, **extra: Any) -> None:
    payload = {"t": int(time.time()), "kind": kind, "detail": detail}
    if extra:
        payload["extra"] = extra
    ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ACTIVITY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_state(**state: Any) -> None:
    payload = {"updated_unix": int(time.time()), **state}
    _write_json(STATE_PATH, payload)


def _seed_checkpoints() -> None:
    checkpoints = _read_json(CHECKPOINTS_PATH, {})
    changed = False
    if "01_truth_surface_demotion" not in checkpoints:
        checkpoints["01_truth_surface_demotion"] = {
            "status": "validated",
            "note": "Founder dashboard demoted fake readiness bars; focused tests passed.",
        }
        changed = True
    if "02_store_agent_primary" not in checkpoints:
        checkpoints["02_store_agent_primary"] = {
            "status": "validated",
            "note": "Store-agent winning path tightened; wiring flag only on real wins.",
        }
        changed = True
    if changed:
        _write_json(CHECKPOINTS_PATH, checkpoints)


def _store_fingerprint() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "exists": STORE_DB.exists(),
        "mtime_ns": None,
        "size": None,
        "total_nodes": None,
    }
    if not STORE_DB.exists():
        return payload
    stat = STORE_DB.stat()
    payload["mtime_ns"] = stat.st_mtime_ns
    payload["size"] = stat.st_size
    try:
        conn = sqlite3.connect(STORE_DB)
        try:
            payload["total_nodes"] = conn.execute(
                "SELECT COUNT(*) FROM memory_nodes"
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception:
        payload["total_nodes"] = None
    return payload


def _ollama(prompt: str, model: str, timeout: int = 180) -> str:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout)).get("response", "").strip()
    except Exception as exc:
        return f"OLLAMA_ERROR: {exc}"


def _list_annotate_live_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["ps", "-Ao", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    matches: list[int] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or "evaluation/annotate_live.py" not in line:
            continue
        parts = line.split(None, 1)
        try:
            pid = int(parts[0])
        except (IndexError, ValueError):
            continue
        if pid == os.getpid():
            continue
        matches.append(pid)
    return matches


def _wait_for_annotate_live_clear() -> None:
    last_blockers: list[int] | None = None
    while True:
        blockers = _list_annotate_live_pids()
        if not blockers:
            if last_blockers:
                _append_activity(
                    "lane_clear",
                    "annotate_live lane cleared; starting eval cycle",
                )
            return
        if blockers != last_blockers:
            _append_activity(
                "lane_blocked",
                "waiting for annotate_live lane to clear",
                blocking_pids=blockers,
            )
        _write_state(
            mode="waiting",
            phase="lane_clear",
            task="03_real_number_runtime",
            blocking_pids=blockers,
            poll_s=WAIT_SLEEP_S,
        )
        last_blockers = blockers
        time.sleep(WAIT_SLEEP_S)


def _run_eval() -> dict[str, Any]:
    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        "evaluation/annotate_live.py",
        "--store",
        str(STORE_DB),
        "--annotations",
        str(GROUND_TRUTH),
        "--reasoner",
        "local-ollama",
        "--repeats",
        "1",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800,
        )
        return {
            "returncode": result.returncode,
            "stdout_tail": result.stdout.strip()[-4000:],
            "stderr_tail": result.stderr.strip()[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout_tail": (exc.stdout or "")[-4000:],
            "stderr_tail": (exc.stderr or "")[-4000:],
            "error": "annotate_live timeout",
        }
    except Exception as exc:
        return {
            "returncode": 1,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": repr(exc),
        }


def _build_report(eval_result: dict[str, Any], store_fp: dict[str, Any]) -> Path:
    store_eval = _read_json(STORE_EVAL, {})
    live44 = _read_json(LIVE44, {})
    ts = time.strftime("%Y%m%d-%H%M%S")
    report_path = REPORTS_DIR / f"cycle-{ts}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "# Serial Chief Cycle Report\n\n"
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "Status: building scout and critic sections from measured artifacts.\n",
        encoding="utf-8",
    )
    prompt_base = (
        "You are a bounded local runtime reviewer for TRACE.\n"
        "Use only the provided measured artifacts.\n"
        "Do not invent causes, files, or outcomes.\n\n"
        f"STORE_FINGERPRINT:\n{json.dumps(store_fp, indent=2)}\n\n"
        f"STORE_EVAL:\n{json.dumps(store_eval, indent=2)}\n\n"
        f"LIVE44:\n{json.dumps(live44, indent=2)}\n\n"
        f"LAST_EVAL_RUN:\n{json.dumps(eval_result, indent=2)}\n"
    )
    scout = _ollama(
        prompt_base
        + "\nReturn 5 bullets max: what is measurably true, what moved, and the top 3 failure signals.",
        SCOUT_MODEL,
    )
    critic = _ollama(
        prompt_base
        + "\nReturn 4 bullets max: the single next bounded patch target, why it dominates, what not to touch, and the exact validation to rerun.",
        CRITIC_MODEL,
        timeout=300,
    )
    report_path.write_text(
        "# Serial Chief Cycle Report\n\n"
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "## Scout\n\n"
        f"{scout}\n\n"
        "## Critic\n\n"
        f"{critic}\n",
        encoding="utf-8",
    )
    return report_path


def _sleep_seconds(before: dict[str, Any], after: dict[str, Any], eval_before: Any, eval_after: Any) -> int:
    moved = (
        before.get("mtime_ns") != after.get("mtime_ns")
        or before.get("size") != after.get("size")
        or before.get("total_nodes") != after.get("total_nodes")
        or eval_before != eval_after
    )
    return SHORT_SLEEP_S if moved else LONG_SLEEP_S


def run_once() -> dict[str, Any]:
    _wait_for_annotate_live_clear()
    before_store = _store_fingerprint()
    before_eval = _read_json(STORE_EVAL, {})
    _write_state(mode="running", phase="eval", task="03_real_number_runtime")
    eval_result = _run_eval()
    after_store = _store_fingerprint()
    after_eval = _read_json(STORE_EVAL, {})
    report_path = _build_report(eval_result, after_store)
    sleep_s = _sleep_seconds(before_store, after_store, before_eval, after_eval)
    _append_activity(
        "cycle_complete",
        "ran annotate_live and refreshed local-LLM reports",
        returncode=eval_result["returncode"],
        sleep_s=sleep_s,
        report=str(report_path),
    )
    return {
        "eval_result": eval_result,
        "before_store": before_store,
        "after_store": after_store,
        "store_eval": after_eval,
        "report": str(report_path),
        "sleep_s": sleep_s,
    }


def main() -> int:
    _seed_checkpoints()
    _append_activity("daemon_start", "serial chief daemon booted")
    while True:
        try:
            cycle = run_once()
            next_wake = int(time.time()) + int(cycle["sleep_s"])
            _write_state(
                mode="sleeping",
                phase="sleep",
                task="03_real_number_runtime",
                sleep_s=cycle["sleep_s"],
                next_wake_unix=next_wake,
                latest_report=cycle["report"],
                latest_store_eval=cycle["store_eval"],
            )
            time.sleep(int(cycle["sleep_s"]))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            retry_unix = int(time.time()) + SHORT_SLEEP_S
            _append_activity(
                "cycle_error",
                "serial chief cycle failed; retrying after short sleep",
                error=repr(exc),
            )
            _write_state(
                mode="error",
                phase="exception",
                task="03_real_number_runtime",
                error=repr(exc),
                next_retry_unix=retry_unix,
            )
            time.sleep(SHORT_SLEEP_S)


if __name__ == "__main__":
    raise SystemExit(main())
