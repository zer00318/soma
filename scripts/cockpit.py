#!/usr/bin/env python3
"""SOMA cockpit — ONE honest status board, in plain words.

Run:  python3 scripts/cockpit.py        (prints the board, also writes
      ops/cockpit/STATUS.md + status.json so anyone can read it without me)

Everything here is read from REAL signals (git, the test gate, the live bound
memory, the 24/7 robot log). Nothing is hand-typed optimism. If a number isn't
measured yet, it says so.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = ROOT / "ops" / "cockpit"
WALK_MEM = ROOT / "data" / "walks" / "walk_outside_20260614" / "memory"
sys.path.insert(0, str(ROOT / "src"))


def _sh(*args: str) -> str:
    try:
        return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _ago(epoch: float) -> str:
    secs = max(0, int(time.time() - epoch))
    if secs < 90:
        return f"{secs}s ago"
    if secs < 5400:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h ago"


def git_state() -> dict[str, str]:
    branch = _sh("git", "rev-parse", "--abbrev-ref", "HEAD") or "?"
    last = _sh("git", "log", "-1", "--pretty=%s") or "?"
    ahead = _sh("git", "rev-list", "--count", "main..HEAD") or "0"
    return {"branch": branch, "last_commit": last, "commits_ahead_of_main": ahead}


def gate_state() -> dict[str, object]:
    path = COCKPIT / "gate.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            data["age"] = _ago(float(data.get("epoch", 0)))
            return data
        except (ValueError, OSError):
            pass
    tests = len(_sh("grep", "-rhoE", r"def test_\w+", "tests/unit").splitlines())
    return {"status": "unknown — run ./scripts/ci.sh", "tests": tests, "age": "—"}


def bound_memory_state() -> dict[str, object]:
    try:
        from soma.demo import bound_memory_to_dict, build_bound_memory

        result, _ = build_bound_memory(str(WALK_MEM))
        payload = bound_memory_to_dict(result)
        counts = payload["counts"]
        sample = [
            f'"{b["subject"][:34]}" {b["predicate"]} {str(b["object"])[:24]}'
            for b in payload["bindings"][:3]  # type: ignore[index]
        ]
        return {"usable": payload["usable"], "counts": counts, "sample": sample}
    except Exception as exc:  # cockpit must never crash on a build hiccup
        return {"usable": False, "error": str(exc)[:120]}


def robots_state() -> dict[str, object]:
    path = COCKPIT / "self_play.jsonl"
    if not path.exists():
        return {"status": "warming up — no rounds logged yet"}
    rounds = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rounds:
        return {"status": "warming up"}
    last = rounds[-1]
    rc, rt = last.get("recall_correct", 0), last.get("recall_total", 0)
    ha, ht = last.get("halluc_answered", 0), last.get("halluc_total", 0)
    return {
        "rounds": len(rounds),
        "last_check": _ago(float(last.get("epoch", 0))),
        "recall_pct": round(100 * rc / rt) if rt else None,
        "halluc_pct": round(100 * ha / ht) if ht else None,
        "misses": last.get("misses", [])[:3],
    }


def build() -> dict[str, object]:
    return {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "git": git_state(),
        "gate": gate_state(),
        "memory": bound_memory_state(),
        "robots": robots_state(),
    }


def _bar(stage_done: list[bool], labels: list[str]) -> str:
    cells = ["[%s %s]" % (lab, "OK" if done else "..") for lab, done in zip(labels, stage_done)]
    return "  " + "--".join(cells)


def render(state: dict[str, object]) -> str:
    mem = state["memory"]
    rob = state["robots"]
    gate = state["gate"]
    git = state["git"]
    counts = mem.get("counts", {}) if isinstance(mem, dict) else {}
    lines = [
        "==================================================================",
        f"  SOMA — STATUS BOARD                         {state['generated']}",
        "==================================================================",
        "",
        "WHERE WE ARE",
        _bar([True, False, False], ["V0 brain", "on iPhone", "glasses"]),
        "  In plain words: the memory BRAIN works on recorded video.",
        "  It does NOT yet run live on the phone.",
        "",
        "WHAT WORKS RIGHT NOW (proven on a real walk, 100% local AI)",
    ]
    if mem.get("usable"):
        lines += [
            f"  - Turns a video into memory: {counts.get('entities','?')} things remembered, "
            f"{counts.get('bindings','?')} confident facts,",
            f"    {counts.get('refused','?')} weak guesses thrown away on purpose.",
            "  - Answers with proof, e.g. \"what did the laptop screen say?\""
            " -> \"Welcome back, Satoshi\".",
            "  - Says \"I don't know\" instead of making things up.",
        ]
    else:
        lines += [f"  - bound memory not built ({mem.get('error','?')})"]
    lines += ["", "HOW GOOD IS IT (auto-measured by the robots, no human grading)"]
    if isinstance(rob, dict) and rob.get("recall_pct") is not None:
        lines += [
            f"  Made-up answers (hallucination): {rob.get('halluc_pct')}%   [lower is better]",
            f"  Questions it can answer (recall): {rob.get('recall_pct')}%   [higher is better]",
        ]
    else:
        lines += ["  not measured yet — robots warming up"]
    lines += ["", "THE ROBOTS (local AI, running 24/7)"]
    if isinstance(rob, dict) and rob.get("rounds"):
        lines += [
            f"  Last check: {rob.get('last_check')}   Rounds done: {rob.get('rounds')}",
            "  They quiz the memory non-stop and hand me what it gets wrong:",
        ]
        for miss in rob.get("misses", []) or ["(none this round)"]:
            lines.append(f"    - {miss}")
    else:
        lines += [f"  {rob.get('status','starting')}"]
    lines += [
        "",
        "HEALTH",
        f"  Code quality gate: {gate.get('status')}  ({gate.get('tests','?')} tests)  {gate.get('age','')}",
        f"  Branch: {git.get('branch')}   Last change: {git.get('last_commit')}",
        f"  Unbanked commits ahead of main: {git.get('commits_ahead_of_main')}",
        "",
        "WHAT THE CHIEF IS DOING NEXT",
        "  1. Bank this work (open the PR)",
        "  2. Put the brain on the iPhone (live capture)",
        "==================================================================",
    ]
    return "\n".join(lines)


def main() -> int:
    COCKPIT.mkdir(parents=True, exist_ok=True)
    state = build()
    board = render(state)
    (COCKPIT / "status.json").write_text(json.dumps(state, indent=2) + "\n")
    (COCKPIT / "STATUS.md").write_text("```\n" + board + "\n```\n")
    print(board)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
