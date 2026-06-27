#!/usr/bin/env python3
"""The ONE job that keeps the cockpit telling the TRUE current story — runs 24/7,
recomputes live numbers every cycle, never hand-edited.

It reads the REAL sources (the store, the running daemons, the eval artifacts) and
writes ops/cockpit/cockpit_state.json, which scripts/cockpit_true.html renders. A
local gemma writes one honest status line per cycle (text-only, fail-soft, so it
never blocks on the GPU). Honesty floor: numbers come from the store/process table,
not from claims; the build-order stage flags below are set conservatively and say
what is VERIFIED vs NOT.

    nohup caffeinate -is .venv/bin/python scripts/cockpit_updater.py \
        --store data/trace_store.sqlite3 --interval 60 \
        > /tmp/trace_cockpit_updater.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ops" / "cockpit" / "cockpit_state.json"

# Build-order stages (founder's foundation-up order). status ∈ verified|partial|todo.
# These qualitative flags are set HONESTLY here; the live numbers are computed each
# cycle. Update a flag only when the underlying reality changes.
BUILD_ORDER = [
    {"key": "capture", "title": "0 · Capture foundation", "status": "partial",
     "note": "Digital pillar (Mac screen→OCR) LIVE 24/7. Offline dense video perceiver "
             "BUILT + verified on real footage (gemma vision, in-memory, 0 frames to disk). "
             "Still TODO: on-device .mov save is broken (never delivered a file to the Mac) "
             "+ phone-screen capture."},
    {"key": "helpers", "title": "1 · Better helpers", "status": "partial",
     "note": "Society of per-frame specialists exists; mislabeling on hard objects unfixed."},
    {"key": "binders", "title": "2 · Binders / before-brain", "status": "partial",
     "note": "Inject layer (fuse→link→expand→tier→compile) built; not yet over the new store."},
    {"key": "brain", "title": "3 · Brain format / reasoner", "status": "todo",
     "note": "Store-grounded reasoner (brain/agent.py) EXISTS but is NOT wired into the live "
             "/ask path, and its accuracy on the new store is UNMEASURED. The only real eval "
             "on record is the live44 battery: RAS 9.1 / 30% hallucination. No 80% claim stands."},
]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _proc_alive(needle: str) -> bool:
    try:
        out = subprocess.run(["ps", "ax"], capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return False
    return any(needle in line and "grep" not in line for line in out.splitlines())


def _store_stats(store_path: str) -> dict:
    stats: dict = {"total": 0, "by_source": {}, "last_obs_age_s": None, "span_min": None}
    try:
        conn = sqlite3.connect(store_path)
        cur = conn.cursor()
        stats["total"] = cur.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
        for src, n in cur.execute("SELECT source, COUNT(*) FROM memory_nodes GROUP BY source"):
            stats["by_source"][src] = n
        row = cur.execute("SELECT MIN(t_ms), MAX(t_ms) FROM memory_nodes").fetchone()
        if row and row[1]:
            stats["last_obs_age_s"] = round(time.time() - row[1] / 1000.0, 1)
            if row[0]:
                stats["span_min"] = round((row[1] - row[0]) / 60000.0, 1)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        stats["error"] = str(exc)
    return stats


def _load_reasoner_eval() -> dict:
    """The reasoner number is a MEASUREMENT or it is UNMEASURED — never a hardcoded claim.
    Reads the real store eval artifact (written by evaluation/annotate_live scorer, task T4).
    Until that file exists, the cockpit shows UNMEASURED, not a flattering guess."""
    path = ROOT / "evaluation" / "ras" / "store_eval.json"
    try:
        data = json.loads(path.read_text())
        return {
            "state": "measured",
            "pct": int(data.get("answered_pct", 0)),
            "halluc_pct": float(data.get("halluc_pct", 100.0)),
            "n": int(data.get("n", 0)),
        }
    except Exception:  # noqa: BLE001  no eval yet -> honest UNMEASURED
        return {"state": "UNMEASURED", "pct": None, "halluc_pct": None, "n": 0}


def _mechanical_progress(store: dict, daemons: dict, reasoner_eval: dict, wired: bool) -> int:
    """Overall progress = a transparent function of REAL signals (store, process table,
    eval artifact, wiring flag). NOT an average of LLM-authored pillar guesses. Every
    point is earned by something a script can verify; it cannot rise on narration alone."""
    pts = 0
    if daemons.get("screen_daemon"):
        pts += 15                                   # digital capture live
    total = int(store.get("total", 0) or 0)
    if total > 0:
        pts += 10                                   # store substrate filling
    if total >= 300:
        pts += 5
    if wired:
        pts += 25                                   # store reasoner IS the live /ask path (T3 flag)
    if reasoner_eval.get("state") == "measured":
        pts += 10                                   # a real number exists at all
        pct = reasoner_eval.get("pct") or 0
        halluc = reasoner_eval.get("halluc_pct")
        halluc = 100.0 if halluc is None else halluc
        if pct >= 75 and halluc < 10:
            pts += 20                               # meets the pitch gate
        elif pct >= 40:
            pts += 10
    # live PHYSICAL capture (the locked demo needs on-device live, NOT video replay)
    if int(store.get("by_source", {}).get("phone_camera", 0) or 0) > 0:
        pts += 15
    return min(pts, 100)


def _gemma_line(state: dict) -> str:
    """One honest status sentence. Text-only, short timeout, fail-soft."""
    rp = state.get("reasoner_pct")
    reasoner_phrase = "reasoner accuracy UNMEASURED" if rp is None else f"reasoner ~{rp}% correct (measured)"
    facts = (f"store has {state['store']['total']} memory nodes "
             f"({state['store'].get('by_source')}); digital daemon alive="
             f"{state['daemons']['screen_daemon']}; last observation "
             f"{state['store'].get('last_obs_age_s')}s ago; {reasoner_phrase}.")
    body = {
        "model": "gemma3:12b-it-qat", "stream": False, "options": {"temperature": 0.2},
        "prompt": "Write ONE plain, honest sentence (<=22 words) a founder can glance at, "
                  "summarizing build progress. No hype, no numbers you weren't given. "
                  f"FACTS: {facts}\nSENTENCE:",
    }
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                     data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=30))["response"].strip()
    except Exception:  # noqa: BLE001  never let the narrator block the cockpit
        return ""


def build_state(store_path: str, narrate: bool) -> dict:
    store = _store_stats(store_path)
    daemons = {
        "screen_daemon": _proc_alive("screen_capture_daemon.py"),
        "brain_server": _proc_alive("trace_brain_server.py"),
        "cockpit_server": _proc_alive("cockpit_ask_server.py"),
    }
    reasoner_eval = _load_reasoner_eval()
    wired = (ROOT / "ops" / "cockpit" / "reasoner_wired.flag").exists()
    state = {
        "updated_unix": int(time.time()),
        "updated_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "store": store,
        "daemons": daemons,
        "reasoner_pct": reasoner_eval["pct"],          # None => UNMEASURED (no hardcoded claim)
        "reasoner_state": reasoner_eval["state"],
        "reasoner_halluc_pct": reasoner_eval["halluc_pct"],
        "overall_progress": _mechanical_progress(store, daemons, reasoner_eval, wired),
        "reasoner_wired_live": wired,
        "build_order": BUILD_ORDER,
        "pillars": {
            "digital": {"state": "live" if daemons["screen_daemon"] else "down",
                        "obs": store["by_source"].get("mac_screen", 0),
                        "how": "Mac screen-grab → Apple Vision OCR → store → image deleted"},
            "physical": {"state": "offline-verified",
                         "obs": store["by_source"].get("phys_video", 0),
                         "how": "saved video → gemma dense perception (in-memory) → store; "
                                "on-device live recorder still broken"},
        },
        "honesty_floor": "<10% confident-wrong (sacred); numbers from store+process table, not claims",
    }
    state["narration"] = _gemma_line(state) if narrate else ""
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="data/trace_store.sqlite3")
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-narrate", action="store_true", help="skip the gemma status line")
    args = ap.parse_args()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    _log(f"cockpit updater up. store={args.store} interval={args.interval}s out={OUT}")
    while True:
        try:
            state = build_state(args.store, narrate=not args.no_narrate)
            OUT.write_text(json.dumps(state, indent=2))
            _log(f"wrote state: {state['store']['total']} nodes "
                 f"(digital={state['pillars']['digital']['obs']}, "
                 f"phys={state['pillars']['physical']['obs']}), "
                 f"screen_daemon={state['daemons']['screen_daemon']}")
        except Exception as exc:  # noqa: BLE001  one bad cycle must not kill the job
            _log(f"cycle error: {exc}")
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
