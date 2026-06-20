#!/usr/bin/env python3
"""Run a persistent Claude supervisor loop with sleep/backoff control.

This wrapper keeps Claude out of the hot path while local workers run.
Claude is only woken when judgment is needed or a scheduled retry time arrives.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_RESET_SLEEP_SECONDS = 5 * 60 * 60 + 5 * 60
DEFAULT_IDLE_SLEEP_SECONDS = 15 * 60
CONTROL_RE = re.compile(r"CONTROL:\s*(\{.*\})\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SOMA Claude supervisor loop.")
    parser.add_argument(
        "--project-root",
        default="/Users/zer00/Documents/VLM",
        help="Project root for the Claude session.",
    )
    parser.add_argument(
        "--prompt-file",
        default="/Users/zer00/Documents/VLM/ops/CLAUDE_SUPERVISOR_PROMPT.md",
        help="Supervisor prompt file.",
    )
    parser.add_argument(
        "--model",
        default="fable",
        help="Claude model alias or full name.",
    )
    parser.add_argument(
        "--session-name",
        default="soma-supervisor",
        help="Friendly Claude session name.",
    )
    parser.add_argument(
        "--state-dir",
        default="/Users/zer00/Documents/VLM/.soma_supervisor",
        help="Directory for persistent supervisor state.",
    )
    parser.add_argument(
        "--idle-sleep-seconds",
        type=int,
        default=DEFAULT_IDLE_SLEEP_SECONDS,
        help="Default sleep when Claude asks to sleep without a value.",
    )
    parser.add_argument(
        "--reset-sleep-seconds",
        type=int,
        default=DEFAULT_RESET_SLEEP_SECONDS,
        help="Sleep time after Claude usage-limit detection.",
    )
    parser.add_argument(
        "--permission-mode",
        default="bypassPermissions",
        choices=["acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan"],
        help="Claude permission mode.",
    )
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        default=True,
        help="Run Claude with bypassed permission checks.",
    )
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def notify(title: str, message: str) -> None:
    safe_title = title.replace('"', "'")
    safe_message = message.replace('"', "'")
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_message}" with title "{safe_title}" sound name "Glass"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def update_state(path: Path, state: dict[str, Any], **updates: Any) -> None:
    state.update(updates)
    state["updated_at"] = int(time.time())
    write_json(path, state)
    # Honest cockpit heartbeat at every supervisor step. Working phases beat with a
    # moderate deadline; sleep/wait phases beat idle with a generous one so a legitimate
    # 5h usage-limit sleep reads "Chief idle", not a false "STOPPED". Best-effort.
    try:
        from cockpit_beat import beat as _beat
        ph = str(updates.get("phase", state.get("phase", "")) or "supervisor")
        idle = any(k in ph for k in ("sleep", "wait", "idle"))
        _beat(ph, 21600 if idle else 1200, by="supervisor", idle=idle)
    except Exception:
        pass


def build_turn_prompt(state: dict[str, Any]) -> str:
    if state.get("turn_count", 0) == 0:
        return (
            "Start autonomous execution now. Audit current repo state, choose the cheapest competent "
            "execution structure, set up delegation if useful, and begin moving SOMA forward immediately."
        )
    return (
        "Continue from your existing state. Do not restart from scratch. "
        "Advance SOMA, delegate aggressively, and return control quickly if local workers or waiting states "
        "mean Claude is not needed right now."
    )


def detect_usage_limit(text: str) -> bool:
    lowered = text.lower()
    signals = [
        "usage limit",
        "rate limit",
        "try again later",
        "5 hours",
        "quota",
    ]
    return any(signal in lowered for signal in signals)


def parse_control(text: str) -> dict[str, Any] | None:
    matches = CONTROL_RE.findall(text)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def run_claude(args: argparse.Namespace, state: dict[str, Any], prompt_text: str) -> tuple[int, str, str]:
    turn_prompt = build_turn_prompt(state)
    cmd = [
        "claude",
        "--model",
        args.model,
        "--session-id",
        state["session_id"],
        "--name",
        args.session_name,
        "--permission-mode",
        args.permission_mode,
        "--append-system-prompt",
        prompt_text,
        "-p",
        turn_prompt,
    ]
    if args.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    proc = subprocess.run(
        cmd,
        cwd=args.project_root,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def wait_for_user_ack(request_file: Path, ack_file: Path, poll_seconds: int = 30) -> None:
    notify("SOMA needs a test", request_file.read_text(encoding="utf-8")[:200])
    while True:
        if ack_file.exists():
            try:
                content = ack_file.read_text(encoding="utf-8").strip()
            except Exception:
                content = ""
            if content:
                return
        time.sleep(poll_seconds)


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root)
    state_dir = Path(args.state_dir)
    prompt_file = Path(args.prompt_file)
    ensure_dir(state_dir)

    log_dir = state_dir / "logs"
    ensure_dir(log_dir)
    state_path = state_dir / "state.json"
    request_file = state_dir / "USER_TEST_REQUEST.txt"
    ack_file = state_dir / "USER_TEST_ACK.txt"

    state = load_json(
        state_path,
        {
            "session_id": str(uuid.uuid4()),
            "turn_count": 0,
            "last_status": "new",
            "last_summary": "",
            "model": args.model,
            "session_name": args.session_name,
        },
    )

    prompt_text = read_text(prompt_file)

    while True:
        state["turn_count"] = int(state.get("turn_count", 0))
        update_state(
            state_path,
            state,
            model=args.model,
            session_name=args.session_name,
            phase="calling_claude",
        )

        returncode, stdout, stderr = run_claude(args, state, prompt_text)
        ts = str(int(time.time()))
        stdout_path = log_dir / f"{ts}.stdout.log"
        stderr_path = log_dir / f"{ts}.stderr.log"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        update_state(
            state_path,
            state,
            last_returncode=returncode,
            last_stdout_log=str(stdout_path),
            last_stderr_log=str(stderr_path),
            phase="processing_result",
        )

        combined = "\n".join(part for part in [stdout, stderr] if part)

        if detect_usage_limit(combined):
            update_state(
                state_path,
                state,
                last_status="usage_limit_sleep",
                last_summary="Claude usage limit hit; sleeping until reset window.",
                phase="sleeping_for_limit_reset",
            )
            notify("SOMA supervisor sleeping", state["last_summary"])
            time.sleep(args.reset_sleep_seconds)
            continue

        if returncode != 0 and not stdout.strip():
            update_state(
                state_path,
                state,
                last_status="error_sleep",
                last_summary=stderr.strip()[:400] or "Claude returned an error.",
                phase="sleeping_after_error",
            )
            notify("SOMA supervisor error", state["last_summary"])
            time.sleep(args.idle_sleep_seconds)
            continue

        control = parse_control(stdout)
        state["turn_count"] += 1

        if control is None:
            update_state(
                state_path,
                state,
                last_status="missing_control",
                last_summary="No control packet found; defaulting to short sleep.",
                phase="sleeping_missing_control",
            )
            time.sleep(5 * 60)
            continue

        status = str(control.get("status", "sleep"))
        summary = str(control.get("summary", "")).strip()
        sleep_seconds = int(control.get("sleep_seconds") or args.idle_sleep_seconds)
        user_request = str(control.get("user_request", "")).strip()

        update_state(
            state_path,
            state,
            last_status=status,
            last_summary=summary,
            next_sleep_seconds=sleep_seconds,
            user_request=user_request,
            phase=f"control_{status}",
        )

        if status == "continue":
            continue

        if status == "sleep":
            update_state(state_path, state, phase="sleeping_idle")
            time.sleep(max(30, sleep_seconds))
            continue

        if status == "user_test":
            request_file.write_text(user_request or summary or "User test requested.", encoding="utf-8")
            ack_file.write_text("", encoding="utf-8")
            update_state(state_path, state, phase="waiting_for_user_test")
            notify("SOMA needs you", user_request or summary or "User test requested.")
            wait_for_user_ack(request_file, ack_file)
            time.sleep(5)
            continue

        if status == "blocked":
            update_state(state_path, state, phase="blocked_wait")
            notify("SOMA supervisor blocked", summary or "Blocked.")
            time.sleep(max(5 * 60, sleep_seconds))
            continue

        if status == "complete":
            update_state(state_path, state, phase="complete")
            notify("SOMA supervisor complete", summary or "SOMA reported complete.")
            return 0

        update_state(state_path, state, phase="sleeping_fallback")
        time.sleep(args.idle_sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
