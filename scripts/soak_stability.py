#!/usr/bin/env python3
"""P-STAB soak rig — stability is a measured number, not a feeling.

Watches three independent liveness signals for N hours and writes one JSONL
tick per interval to evaluation/soak_history.jsonl:

  1. device process  — `devicectl device info processes`: is the app PID alive?
                       A PID change between ticks = crash+relaunch; a missing
                       PID = dead. Either way the rig pulls the newest .ips
                       from systemCrashLogs AND Documents/crash_blackbox.log
                       from the app container into evaluation/soak_artifacts/,
                       so every death arrives with its own evidence.
  2. hub health      — GET /health (lock-free endpoint, M7): alive + latency.
  3. ingest heartbeat— row-count delta in the sqlite store. The phone can only
                       feed rows while unlocked+capturing, so a gap is REPORTED
                       (honest signal), but only crashes fail the soak.

Verdict: PASS iff zero app deaths and hub alive on every tick.
Exit 0 on PASS, 1 on FAIL — usable as the P-STAB merge gate.

Usage:
  .venv/bin/python scripts/soak_stability.py --hours 4            # the gate
  .venv/bin/python scripts/soak_stability.py --hours 0.05 --dry   # rig self-test
  --relaunch   relaunch the app after a detected death (keeps soak going;
               each death still counts as a failure)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DEVICE_UUID = "D3A506B2-8923-5313-B8A3-FF769ABBA228"  # Right's iPhone (coredevice)
BUNDLE_ID = "de.zer00.trace"
PROC_NAME = "FastVLM App"
HISTORY = REPO / "evaluation" / "soak_history.jsonl"
ARTIFACTS = REPO / "evaluation" / "soak_artifacts"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def devicectl(*args: str, timeout: int = 45) -> dict | None:
    """Run a devicectl subcommand with --json-output and return the parsed JSON."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name
    cmd = ["xcrun", "devicectl", *args, "--device", DEVICE_UUID,
           "--json-output", out_path, "--quiet"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
        with open(out_path) as fh:
            return json.load(fh)
    except Exception:
        return None
    finally:
        pathlib.Path(out_path).unlink(missing_ok=True)


PROBE_ERROR = -1  # devicectl itself failed — NOT evidence of app death


def app_pid() -> int | None:
    """pid if the app is listed, None if the device answered and the app is
    definitively absent, PROBE_ERROR if devicectl itself failed. Soak #1's
    second 'death' (tick 431) was a probe timeout counted as a death — the
    same PID was alive 25 min later. A failed probe is silence, not absence."""
    data = devicectl("device", "info", "processes")
    if not data:
        return PROBE_ERROR
    procs = data.get("result", {}).get("runningProcesses", [])
    if not procs:
        return PROBE_ERROR  # an empty list from a live phone is not credible
    for proc in procs:
        # executable is a file:// URL — spaces arrive as %20
        exe = urllib.parse.unquote(proc.get("executable", "") or "")
        if PROC_NAME in exe:
            return proc.get("processIdentifier")
    return None


def hub_health(hub: str) -> tuple[bool, float | None]:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(f"{hub}/health", timeout=5) as resp:
            ok = resp.status == 200
        return ok, round(time.monotonic() - t0, 3)
    except Exception:
        return False, None


def store_rows(store: pathlib.Path) -> int | None:
    if not store.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=3)
        try:
            return con.execute("SELECT count(*) FROM memory_nodes").fetchone()[0]
        finally:
            con.close()
    except Exception:
        return None


def newest_crash_report() -> str | None:
    """Name of the newest FastVLM .ips in systemCrashLogs, or None."""
    data = devicectl("device", "info", "files",
                     "--domain-type", "systemCrashLogs", "--no-recurse")
    if not data:
        return None
    names = [f.get("name", "") for f in
             data.get("result", {}).get("files", [])]
    ours = sorted(n for n in names if PROC_NAME in n and n.endswith(".ips"))
    return ours[-1] if ours else None


def pull_evidence(tag: str) -> list[str]:
    """After a death: pull newest .ips + crash_blackbox.log into ARTIFACTS."""
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    pulled: list[str] = []
    ips = newest_crash_report()
    if ips:
        dest = ARTIFACTS / f"{tag}-{ips}"
        devicectl("device", "copy", "from", "--domain-type", "systemCrashLogs",
                  "--source", ips, "--destination", str(dest))
        if dest.exists():
            pulled.append(str(dest.relative_to(REPO)))
    bb_dest = ARTIFACTS / f"{tag}-crash_blackbox.log"
    devicectl("device", "copy", "from",
              "--domain-type", "appDataContainer",
              "--domain-identifier", BUNDLE_ID,
              "--source", "Documents/crash_blackbox.log",
              "--destination", str(bb_dest))
    if bb_dest.exists():
        pulled.append(str(bb_dest.relative_to(REPO)))
    return pulled


def relaunch_app() -> bool:
    data = devicectl("device", "process", "launch", BUNDLE_ID, timeout=60)
    return bool(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--interval", type=int, default=30, help="seconds per tick")
    ap.add_argument("--hub", default="http://127.0.0.1:8765")
    ap.add_argument("--store", default=str(REPO / "data" / "trace_store.sqlite3"))
    ap.add_argument("--relaunch", action="store_true")
    ap.add_argument("--dry", action="store_true",
                    help="rig self-test: run ticks, never touch verdict gate")
    args = ap.parse_args()

    store = pathlib.Path(args.store)
    deadline = time.monotonic() + args.hours * 3600
    run_id = dt.datetime.now().strftime("soak-%Y%m%d-%H%M%S")

    last_pid = app_pid()
    last_rows = store_rows(store)
    deaths = 0
    hub_failures = 0
    ticks = 0
    max_ingest_gap_s = 0
    last_ingest_t = time.monotonic()

    print(f"[{run_id}] soak start: pid={last_pid} rows={last_rows} "
          f"hours={args.hours} interval={args.interval}s relaunch={args.relaunch}")

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    while time.monotonic() < deadline:
        time.sleep(args.interval)
        ticks += 1
        pid = app_pid()
        hub_ok, hub_latency = hub_health(args.hub)
        rows = store_rows(store)

        event = None
        evidence: list[str] = []
        if pid == PROBE_ERROR:
            event = "PROBE_ERROR"  # counted separately; never a death
            pid = last_pid        # carry the last known state through the gap
        elif last_pid is not None and last_pid != PROBE_ERROR and pid != last_pid:
            deaths += 1
            event = "APP_DIED" if pid is None else "APP_PID_CHANGED"
            evidence = pull_evidence(f"{run_id}-death{deaths}")
        # Relaunch on EVERY dead tick, not only the death-transition tick — the
        # first live death (2026-07-05 21:15, lifecycle reap) hit a failed launch
        # and the old transition-only logic never tried again for the rest of
        # the soak. A dead app that stays dead is a rig bug, not a measurement.
        if pid is None and args.relaunch and relaunch_app():
            time.sleep(5)
            pid = app_pid()
            event = (event + "+RELAUNCHED") if event else "RELAUNCHED"
        if not hub_ok:
            hub_failures += 1

        if rows is not None and last_rows is not None and rows > last_rows:
            last_ingest_t = time.monotonic()
        gap = int(time.monotonic() - last_ingest_t)
        max_ingest_gap_s = max(max_ingest_gap_s, gap)

        tick = {
            "ts": now_iso(), "run": run_id, "tick": ticks, "pid": pid,
            "hub_ok": hub_ok, "hub_latency_s": hub_latency, "rows": rows,
            "ingest_gap_s": gap, "event": event, "evidence": evidence,
        }
        with HISTORY.open("a") as fh:
            fh.write(json.dumps(tick) + "\n")
        if event:
            print(f"[{run_id}] tick {ticks}: {event} evidence={evidence}")
        last_pid, last_rows = pid, rows

    verdict = "PASS" if deaths == 0 and hub_failures == 0 else "FAIL"
    summary = {
        "ts": now_iso(), "run": run_id, "summary": True, "verdict": verdict,
        "ticks": ticks, "deaths": deaths, "hub_failures": hub_failures,
        "max_ingest_gap_s": max_ingest_gap_s, "hours": args.hours,
    }
    with HISTORY.open("a") as fh:
        fh.write(json.dumps(summary) + "\n")
    print(f"[{run_id}] {verdict}: ticks={ticks} deaths={deaths} "
          f"hub_failures={hub_failures} max_ingest_gap={max_ingest_gap_s}s")
    if args.dry:
        return 0
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
