#!/usr/bin/env python3
"""TRACE night shift — local-LLM task runner with verification gates.

Claude (lead) writes the task queue (ops/night_shift_queue.json) with
precise single-file specs; this harness makes the local models execute
them safely while no Claude session is running:

  - kind "code":    qwen2.5-coder:14b drafts ONE whole file from the spec;
                    the verify command must exit 0 or the attempt is rolled
                    back and retried with the error fed back (max_attempts).
                    Passing work is git-committed immediately.
  - kind "founder": writes the request to /tmp/trace_founder_request.txt and
                    fires a macOS notification; the founder does the IRL
                    step and replies:  echo done > /tmp/trace_founder_reply.txt
  - kind "gate":    a shell command that must pass (tests, eval, device
                    checks). Gates with "blocking": false log failures and
                    continue; blocking gates stop the shift (safety).

Rules encoded here, not trusted to the model: single-file writes only,
backup+rollback around every attempt, sequential ollama calls (one model
in VRAM at a time), full test suite as the standing gate, everything
logged to /tmp/trace_night_shift.log and state to ops/night_shift_state.json.

Run:  nohup python3 scripts/trace_night_shift.py > /dev/null 2>&1 &
Stop: pkill -f trace_night_shift
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path("/Users/zer00/Documents/VLM")
QUEUE = ROOT / "ops" / "night_shift_queue.json"
STATE = ROOT / "ops" / "night_shift_state.json"
LOG = Path("/tmp/trace_night_shift.log")
REQUEST = Path("/tmp/trace_founder_request.txt")
REPLY = Path("/tmp/trace_founder_reply.txt")
OLLAMA = "http://127.0.0.1:11434/api/generate"
CODE_MODEL = "qwen3-coder:30b"

SYSTEM_RULES = """You are a careful implementation worker on the TRACE codebase.
Write the COMPLETE content of exactly one file. Rules:
- Output ONLY the file content inside one ```...``` fenced block. No prose.
- Standard library + explicitly allowed imports only. No placeholders, no TODO.
- Follow the spec exactly; if the spec gives function signatures, match them.
- The file must be self-verifiable via the stated verify command.
- Target Python is 3.9: the FIRST line of imports in every Python file MUST
  be `from __future__ import annotations`. Never use `X | Y` unions or
  builtin generics in runtime expressions (isinstance, defaults) — only in
  annotations. No match statements.
"""


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def notify(title: str, body: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{body[:120]}" with title "{title[:60]}" sound name "Glass"'],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"tasks": {}}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


def llm(prompt: str, timeout: int = 900) -> str:
    payload = json.dumps({
        "model": CODE_MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": 6000},
    }).encode()
    req = urllib.request.Request(OLLAMA, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("response", "")


def extract_code(reply: str) -> str | None:
    blocks = re.findall(r"```[a-zA-Z0-9]*\n(.*?)```", reply, re.DOTALL)
    if not blocks:
        return None
    return max(blocks, key=len).rstrip() + "\n"


def run(cmd: str, timeout: int = 1200) -> tuple[int, str]:
    p = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-3000:]


def git_commit(path: str, message: str) -> None:
    run(f'git add "{path}" ops/night_shift_state.json 2>/dev/null; '
        f'git commit -m "night-shift: {message}\n\n'
        f'Co-Authored-By: qwen2.5-coder night shift <noreply@local>" --no-verify')


def do_code(task: dict) -> bool:
    target = ROOT / task["target_file"]
    backup = target.read_text() if target.exists() else None
    error_feedback = ""
    for attempt in range(1, int(task.get("max_attempts", 3)) + 1):
        log(f"  code attempt {attempt} for {task['id']}")
        prompt = (
            SYSTEM_RULES
            + f"\n## Task: {task['title']}\n## Target file: {task['target_file']}\n"
            + f"## Spec\n{task['spec']}\n"
        )
        if backup:
            prompt += f"\n## Current file content (you may rewrite fully)\n```\n{backup[:12000]}\n```\n"
        if error_feedback:
            prompt += f"\n## Your previous attempt FAILED verification with\n{error_feedback}\nFix it.\n"
        try:
            reply = llm(prompt)
        except Exception as exc:
            log(f"  ollama error: {exc}; waiting 120s")
            time.sleep(120)
            continue
        code = extract_code(reply)
        if not code or len(code) < 80:
            error_feedback = "No usable fenced code block was produced."
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code)
        rc, out = run(task["verify"])
        if rc == 0:
            log(f"  VERIFIED: {task['id']} ({task['verify']})")
            git_commit(task["target_file"], f"{task['id']} {task['title']}")
            return True
        error_feedback = out
        log(f"  verify failed (rc={rc}): {out[-300:]}")
    # final failure: restore original so the tree stays green
    if backup is not None:
        target.write_text(backup)
    elif target.exists():
        target.unlink()
    return False


def do_founder(task: dict) -> bool:
    REQUEST.write_text(
        f"TRACE NIGHT SHIFT needs you ({task['id']}):\n\n{task['message']}\n\n"
        f"When done, run:  echo done > {REPLY}\n"
    )
    REPLY.unlink(missing_ok=True)
    log(f"  founder request posted: {task['title']}")
    notify("TRACE needs you", task["title"])
    waited = 0
    while not REPLY.exists():
        time.sleep(30)
        waited += 30
        if waited % 1800 == 0:  # re-ping every 30 min
            notify("TRACE still waiting", task["title"])
    answer = REPLY.read_text().strip()
    REPLY.unlink(missing_ok=True)
    log(f"  founder replied: {answer[:160]}")
    return True


def do_gate(task: dict) -> bool:
    rc, out = run(task["verify"])
    log(f"  gate {task['id']} rc={rc}: {out[-200:]}")
    return rc == 0


def main() -> None:
    queue = json.loads(QUEUE.read_text())
    state = load_state()
    log(f"night shift starting: {len(queue['tasks'])} tasks")
    for task in queue["tasks"]:
        tid = task["id"]
        st = state["tasks"].get(tid, {})
        if st.get("status") == "done":
            continue
        log(f"TASK {tid}: {task['title']} [{task['kind']}]")
        state["tasks"][tid] = {"status": "running", "started": datetime.now().isoformat()}
        save_state(state)
        ok = {"code": do_code, "founder": do_founder, "gate": do_gate}[task["kind"]](task)
        state["tasks"][tid] = {
            "status": "done" if ok else "failed",
            "finished": datetime.now().isoformat(),
        }
        save_state(state)
        if not ok:
            log(f"TASK {tid} FAILED")
            if task.get("blocking", True):
                notify("TRACE night shift blocked", f"{tid} failed — see log")
                log("blocking task failed — stopping shift (tree left green)")
                return
    notify("TRACE night shift complete", "All tasks finished")
    log("night shift complete")


if __name__ == "__main__":
    main()
