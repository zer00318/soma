#!/usr/bin/env python3
"""Autonomous coding worker — uses local gemma3:27b to implement features.

Picks tasks from TASK_QUEUE, prompts gemma3 to write code improvements,
patches the target file, runs tests, and reports live progress to
/tmp/trace_worker_state.json (polled by cockpit every 3s).

    .venv/bin/python scripts/autonomous_worker.py [--once] [--task N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_FILE = Path("/tmp/trace_worker_state.json")
LOG_FILE = Path("/tmp/trace_worker.log")
OLLAMA = "http://127.0.0.1:11434"
MODEL = "gemma3:27b-it-qat"
VENV_PY = str(REPO / ".venv/bin/python3")

# ---------------------------------------------------------------------------
# Task queue — each task has a target file, a description of what to improve,
# the specific context to read, and a verification command.
# ---------------------------------------------------------------------------
# Tasks target COMPLETE NAMED functions (the splicer replaces whole functions, not
# fragments — proven limitation). Each is gated by a real acceptance test it must turn
# green. Propose-only: a green patch is stashed in ops/worker_patches/ for Chief review.
TASK_QUEUE = [
    # ════════════════════════════════════════════════════════════════════════
    # LIQUIDATED 2026-06-27 (Commander-in-Chief). The activity/specialist/instance-
    # graph tasks were the REJECTED schematized abstraction. This single-function-
    # splice worker fits ISOLATED stub-fills only; the pitch-critical work is multi-
    # function and Chief-led. Serial plan: ops/SERIAL_EXECUTION_LEDGER_2026-06-27.md.
    # Do NOT repopulate with the old tasks. Chief lays one isolated task here at a time.
    # ════════════════════════════════════════════════════════════════════════
]


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def _write_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def _clear_state() -> None:
    _write_state({"active": False, "heartbeat": time.time()})


def _ollama_generate(prompt: str, on_token=None) -> str:
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": True,
        "options": {"temperature": 0.15, "num_predict": 4096},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=body,
        headers={"content-type": "application/json"},
    )
    full = []
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            chunk = json.loads(raw.decode())
            tok = chunk.get("response", "")
            full.append(tok)
            if on_token and tok:
                on_token(tok)
            if chunk.get("done"):
                break
    return "".join(full)


def _read_file_excerpt(path: str, lines: tuple[int, int] | None) -> str:
    p = REPO / path
    if not p.exists():
        return f"# FILE NOT FOUND: {path}"
    text = p.read_text()
    if lines:
        all_lines = text.splitlines()
        start = max(0, lines[0] - 1)
        end = min(len(all_lines), lines[1])
        excerpt = "\n".join(all_lines[start:end])
        return f"# {path} (lines {lines[0]}-{lines[1]}):\n{excerpt}"
    return f"# {path}:\n{text}"


def _extract_python_block(text: str) -> str | None:
    """Extract the first ```python ... ``` block from LLM output."""
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Fallback: any ``` block
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    return None


def _run_verify(task: dict) -> tuple[bool, str]:
    cmd = task["verify"]
    timeout = task.get("verify_timeout", 120)
    try:
        result = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout
        )
        passed = result.returncode == 0
        out = (result.stdout + result.stderr).strip()[-800:]
        return passed, out
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def _func_spans(src: str) -> dict[str, tuple[int, int]]:
    """Map top-level function name -> (start_line, end_line) 1-based inclusive."""
    import ast
    spans: dict[str, tuple[int, int]] = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return spans
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None)
            if end is None:
                continue
            # include leading decorators
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            spans[node.name] = (start, end)
    return spans


def _replace_functions(original: str, new_code: str) -> tuple[str, list[str]]:
    """Splice gemma's complete function definitions into the original source by
    NAME. Returns (modified_source, replaced_names). Functions present in new_code
    but absent in original are ignored (we don't blindly append top-level code).
    Order-preserving and indentation-safe because we swap whole line ranges."""
    new_spans = _func_spans(new_code)
    if not new_spans:
        return original, []
    new_lines = new_code.splitlines()
    orig_lines = original.splitlines()
    orig_spans = _func_spans(original)

    replaced: list[str] = []
    # Apply replacements from the BOTTOM up so earlier line numbers stay valid.
    for name in sorted(new_spans, key=lambda n: orig_spans.get(n, (1 << 30,))[0], reverse=True):
        if name not in orig_spans:
            continue
        o_start, o_end = orig_spans[name]
        n_start, n_end = new_spans[name]
        replacement = new_lines[n_start - 1:n_end]
        orig_lines[o_start - 1:o_end] = replacement
        replaced.append(name)
    return "\n".join(orig_lines) + "\n", replaced


def _run_verify_in(task: dict, root: Path) -> tuple[bool, str]:
    """Run the task's gate test with `root` as cwd/PYTHONPATH so an isolated copy's
    modules shadow the live ones. The live repo is never imported or mutated."""
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH','')}"
    # Absolutize a relative venv python so the command survives cwd=root.
    cmd = list(task["verify"])
    if cmd and cmd[0].startswith(".venv/"):
        cmd[0] = str(REPO / cmd[0])
    try:
        r = subprocess.run(cmd, cwd=str(root), capture_output=True,
                           text=True, timeout=task.get("verify_timeout", 120), env=env)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-800:]
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def _apply_and_gate(task: dict, code: str, autoapply: bool) -> dict:
    """COPY-SAFE gating: splice gemma's functions into an ISOLATED copy of the repo,
    run the gate there, and only touch live source if (green AND autoapply). The live
    file is never mutated during gating — a killed worker can't leave unverified code
    in the tree. Verified-but-not-applied patches are stashed for Chief review."""
    import ast
    import difflib
    import shutil
    import tempfile

    target_rel = task["read_file"]
    live = REPO / target_rel
    backup = live.read_text()

    modified, replaced = _replace_functions(backup, code)
    if not replaced:
        return {"outcome": "no_match", "replaced": [],
                "note": "no matching top-level functions to splice"}
    try:
        ast.parse(modified)
    except SyntaxError as e:
        return {"outcome": "syntax_error", "replaced": replaced,
                "note": f"spliced source won't parse: {e}"}

    tmp = Path(tempfile.mkdtemp(prefix="trace_gate_"))
    try:
        # Minimal isolated repo: copy code + tests + config, symlink read-only fixtures.
        for d in ("scripts", "tests"):
            if (REPO / d).exists():
                shutil.copytree(REPO / d, tmp / d)
        for f in ("pyproject.toml", "pytest.ini", "conftest.py"):
            if (REPO / f).exists():
                shutil.copy2(REPO / f, tmp / f)
        if (REPO / "data").exists():
            (tmp / "data").symlink_to(REPO / "data")
        # baseline (unmodified copy) then with the splice applied
        before_pass, _ = _run_verify_in(task, tmp)
        (tmp / target_rel).write_text(modified)
        after_pass, after_out = _run_verify_in(task, tmp)
        # Regression gate for auto-apply: the FULL suite must also pass in isolation,
        # so a patch that fixes its task but breaks something else can never land.
        regression_ok = True
        if after_pass and autoapply:
            full = {"verify": [VENV_PY, "-m", "pytest", "tests", "-q"], "verify_timeout": 300}
            regression_ok, _ = _run_verify_in(full, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    diff = "\n".join(difflib.unified_diff(
        backup.splitlines(), modified.splitlines(),
        fromfile=target_rel, tofile=target_rel + " (worker)", lineterm=""))[:4000]
    improved = after_pass and not before_pass

    if after_pass and autoapply and regression_ok:
        live.write_text(modified)  # only now does anything touch the live tree
        outcome = "applied"
    else:
        outcome = "proposed" if after_pass else "rejected"
        if after_pass:
            pdir = REPO / "ops" / "worker_patches"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"{task['id']}.diff").write_text(diff)

    return {"outcome": outcome, "replaced": replaced, "before_pass": before_pass,
            "after_pass": after_pass, "improved": improved, "diff": diff,
            "test_out": after_out[-400:]}


def _build_prompt(task: dict) -> str:
    excerpt = _read_file_excerpt(task["read_file"], task.get("read_lines"))
    return f"""You are a Python engineer improving a multi-modal perception pipeline called TRACE.
The pipeline captures scenes from a wearable camera and answers questions about what was seen.

## Your task: {task['title']}

{task['description']}

## Current code to modify:

{excerpt}

## Instructions:
- Output ONLY the COMPLETE modified version of the functions/sections that need changing
- Wrap your code in ```python ... ``` markers
- Do not change unrelated code
- Do not add import statements that are already present
- Keep all existing docstrings and comments unless directly related to the change
- Be surgical: change only what is described in the task
- After the code block, write a one-line summary of what you changed

Write the improved code now:"""


def run_task(task: dict, dry_run: bool = False) -> bool:
    _log(f"STARTING: [{task['id']}] {task['title']}")

    tokens_so_far: list[str] = []
    last_state_update = time.time()

    def on_token(tok: str) -> None:
        nonlocal last_state_update
        tokens_so_far.append(tok)
        now = time.time()
        if now - last_state_update > 1.0:
            snippet = "".join(tokens_so_far[-120:]).replace("\n", " ")
            _write_state({
                "active": True,
                "task_id": task["id"],
                "helper": task["helper"],
                "title": task["title"],
                "phase": "writing_code",
                "tokens_written": len(tokens_so_far),
                "preview": snippet,
                "heartbeat": now,
            })
            last_state_update = now

    _write_state({
        "active": True,
        "task_id": task["id"],
        "helper": task["helper"],
        "title": task["title"],
        "phase": "reading_context",
        "tokens_written": 0,
        "preview": "Reading file context…",
        "heartbeat": time.time(),
    })

    prompt = _build_prompt(task)
    _log(f"Prompting {MODEL} ({len(prompt)} chars)…")

    try:
        response = _ollama_generate(prompt, on_token=on_token)
    except Exception as e:
        _log(f"OLLAMA ERROR: {e}")
        _write_state({
            "active": False,
            "task_id": task["id"],
            "helper": task["helper"],
            "title": task["title"],
            "phase": "error",
            "error": str(e),
            "heartbeat": time.time(),
        })
        return False

    _log(f"Got {len(response)} chars from model")
    code = _extract_python_block(response)
    if not code:
        _log("WARNING: no python code block found in response")
        _write_state({
            "active": False,
            "task_id": task["id"],
            "helper": task["helper"],
            "title": task["title"],
            "phase": "done_no_code",
            "preview": response[:300],
            "heartbeat": time.time(),
        })
        return False

    _write_state({
        "active": True,
        "task_id": task["id"],
        "helper": task["helper"],
        "title": task["title"],
        "phase": "verifying",
        "tokens_written": len(tokens_so_far),
        "preview": "Running tests…",
        "heartbeat": time.time(),
    })

    if dry_run:
        _log("DRY RUN — skipping file write and verification")
        print("\n=== Generated code ===\n")
        print(code[:2000])
        return True

    # Save generated code to a scratchpad for review before patching
    scratch = Path("/tmp/trace_worker_patch.py")
    scratch.write_text(f"# Task: {task['id']}\n# File: {task['read_file']}\n\n{code}")

    # REAL apply-gate-revert: splice gemma's functions in, run the gate test,
    # keep only if green AND autoapply (env WORKER_AUTOAPPLY=1); else revert.
    autoapply = os.environ.get("WORKER_AUTOAPPLY") == "1"
    res = _apply_and_gate(task, code, autoapply)
    passed = res.get("after_pass", False)
    outcome = res["outcome"]
    _log(f"GATE: outcome={outcome} before_pass={res.get('before_pass')} "
         f"after_pass={passed} improved={res.get('improved')} "
         f"replaced={res.get('replaced')} {res.get('note','')}")

    summary_line = response.split("```")[-1].strip()[:200] if "```" in response else ""
    _write_state({
        "active": False,
        "task_id": task["id"],
        "helper": task["helper"],
        "title": task["title"],
        "phase": "done",
        "tests_passed": passed,
        "outcome": outcome,
        "improved": res.get("improved", False),
        "replaced": res.get("replaced", []),
        "summary": summary_line,
        "code_preview": code[:400],
        "heartbeat": time.time(),
        "completed_at": time.strftime("%H:%M:%S"),
    })

    return passed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run one task and exit")
    ap.add_argument("--task", type=int, default=0, help="Task index to run (0-based)")
    ap.add_argument("--dry-run", action="store_true", help="Print code but don't patch")
    ap.add_argument("--list", action="store_true", help="List available tasks")
    args = ap.parse_args()

    if args.list:
        for i, t in enumerate(TASK_QUEUE):
            print(f"[{i}] {t['id']}: {t['title']}")
        return 0

    _log(f"autonomous_worker START pid={os.getpid()} model={MODEL}")

    if args.once:
        task = TASK_QUEUE[args.task]
        ok = run_task(task, dry_run=args.dry_run)
        return 0 if ok else 1

    # Continuous loop: cycle through tasks; skip ones whose gate is already green so
    # we never burn gemma (or churn) on finished work — idle honestly when the queue is done.
    pause_flag = REPO / "ops" / "worker_paused"
    idx = 0
    consecutive_green = 0
    while True:
        if pause_flag.exists():
            _write_state({"active": False, "phase": "paused", "heartbeat": time.time(),
                          "note": "ops/worker_paused present — executor paused by Chief"})
            time.sleep(15)
            continue
        task = TASK_QUEUE[idx % len(TASK_QUEUE)]
        already_green, _ = _run_verify(task)
        if already_green:
            consecutive_green += 1
            if consecutive_green >= len(TASK_QUEUE):  # whole queue done -> idle
                _write_state({"active": False, "phase": "idle", "heartbeat": time.time(),
                              "note": "all queued tasks pass their gate — nothing to grind"})
                time.sleep(30)
                consecutive_green = 0  # re-check periodically in case a gate goes red
            idx += 1
            continue
        consecutive_green = 0
        run_task(task, dry_run=args.dry_run)
        idx += 1
        _write_state({"active": False, "phase": "sleeping", "heartbeat": time.time(),
                      "next_task": TASK_QUEUE[idx % len(TASK_QUEUE)]["title"]})
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
