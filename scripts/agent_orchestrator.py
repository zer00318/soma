#!/usr/bin/env python3
"""Local-LLM AGENT TEAM that actually does sprint work + reports live status.

The founder wants to SEE the team working: who is alive, what each is doing right
now, and the bar moving. This is that team — a scheduler driving named local-LLM
agents (ollama gemma 12b/27b). The M2 OOMs on concurrent gemma, so the GPU agents
share a mutex (one at a time); the no-GPU Metrics agent runs free, so there is
always genuine parallel activity to show.

Agents:
  Metrics    (no GPU)        live store/rate numbers every few seconds
  Perceiver  (gemma3:12b VL) backfills PHYSICAL obs from saved walk videos (bar moves)
  Evaluator  (gemma3:12b)    asks the reasoner sample Qs over the store -> answerability
  Planner    (gemma3:27b)    refreshes project_plan.json progress/status from real signals
  Scribe     (gemma3:12b)    writes the honest one-line narration + activity digests

Outputs (read by the founder dashboard):
  ops/cockpit/agents_live.json     per-agent status + heartbeat + last result
  ops/cockpit/agent_activity.jsonl append-only feed of what the team did
  ops/cockpit/cockpit_state.json   live numbers (also written by cockpit_updater)
  ops/cockpit/project_plan.json    decomposition (Planner keeps progress fresh)

    nohup caffeinate -is .venv/bin/python scripts/agent_orchestrator.py \
        > /tmp/trace_orchestrator.log 2>&1 &
"""
from __future__ import annotations

import base64
import json
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COCK = ROOT / "ops" / "cockpit"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

STORE = str(ROOT / "data" / "trace_store.sqlite3")
WALKS = [str(p) for p in (ROOT / "data" / "walks").glob("*.[mM][oO][vV]")]

AGENTS_LIVE = COCK / "agents_live.json"
ACTIVITY = COCK / "agent_activity.jsonl"
STATE = COCK / "cockpit_state.json"
PLAN = COCK / "project_plan.json"

HOST = "http://127.0.0.1:11434"
GPU = threading.Lock()           # one gemma at a time (M2 OOM guard)
_LOCK = threading.Lock()         # guards the in-memory agent table

# ---- agent table (in memory, mirrored to disk) ----------------------------------
_AGENTS: dict[str, dict] = {
    "Metrics":   {"role": "live numbers", "model": "—", "status": "idle", "task": "", "started": 0, "beat": 0, "done": 0, "last": ""},
    "Perceiver": {"role": "physical perception", "model": "gemma3:12b", "status": "idle", "task": "", "started": 0, "beat": 0, "done": 0, "last": ""},
    "Evaluator": {"role": "answerability eval", "model": "gemma3:12b", "status": "idle", "task": "", "started": 0, "beat": 0, "done": 0, "last": ""},
    "Planner":   {"role": "plan + progress", "model": "gemma3:27b", "status": "idle", "task": "", "started": 0, "beat": 0, "done": 0, "last": ""},
    "Scribe":    {"role": "narration", "model": "gemma3:12b", "status": "idle", "task": "", "started": 0, "beat": 0, "done": 0, "last": ""},
}


def _now() -> int:
    return int(time.time())


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _set(agent: str, **kw) -> None:
    with _LOCK:
        _AGENTS[agent].update(kw, beat=_now())


def _flush_agents() -> None:
    with _LOCK:
        rows = [{"name": n, **v} for n, v in _AGENTS.items()]
    AGENTS_LIVE.write_text(json.dumps({"updated_unix": _now(), "agents": rows}, indent=2))


def _activity(agent: str, action: str, detail: str = "") -> None:
    line = json.dumps({"t": _now(), "agent": agent, "action": action, "detail": detail[:200]})
    with ACTIVITY.open("a") as fh:
        fh.write(line + "\n")


def _gen(model: str, prompt: str, images=None, timeout: int = 60) -> str:
    body = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
    if images:
        body["images"] = images
    req = urllib.request.Request(f"{HOST}/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()


# ---- shared store stats ---------------------------------------------------------
_rate_window: list[tuple[int, int]] = []  # (unix, total) samples for obs/min


def _store_stats() -> dict:
    st = {"total": 0, "by_source": {}, "last_obs_age_s": None, "obs_per_min": 0.0}
    try:
        c = sqlite3.connect(STORE)
        st["total"] = c.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
        for s, n in c.execute("SELECT source, COUNT(*) FROM memory_nodes GROUP BY source"):
            st["by_source"][s] = n
        row = c.execute("SELECT MAX(t_ms) FROM memory_nodes").fetchone()
        if row and row[0]:
            st["last_obs_age_s"] = round(time.time() - row[0] / 1000.0, 1)
        c.close()
    except Exception as e:  # noqa: BLE001
        st["error"] = str(e)
    now = _now()
    _rate_window.append((now, st["total"]))
    while _rate_window and now - _rate_window[0][0] > 300:
        _rate_window.pop(0)
    if len(_rate_window) >= 2:
        dt = _rate_window[-1][0] - _rate_window[0][0]
        dn = _rate_window[-1][1] - _rate_window[0][1]
        st["obs_per_min"] = round(dn / dt * 60, 2) if dt else 0.0
    return st


def _proc(needle: str) -> bool:
    try:
        out = subprocess.run(["ps", "ax"], capture_output=True, text=True, timeout=8).stdout
        return any(needle in l and "grep" not in l for l in out.splitlines())
    except Exception:  # noqa: BLE001
        return False


# ---- AGENT: Metrics (no GPU) ----------------------------------------------------
def run_metrics() -> None:
    _set("Metrics", status="working", task="recompute live numbers", started=_now())
    st = _store_stats()
    daemons = {
        "screen_daemon": _proc("screen_capture_daemon.py"),
        "brain_server": _proc("trace_brain_server.py"),
        "orchestrator": True,
    }
    reasoner = _read_reasoner_eval()
    wired = (COCK / "reasoner_wired.flag").exists()
    state = {
        "updated_unix": _now(), "updated_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "store": st, "daemons": daemons,
        "overall_progress": _mechanical_overall(st, daemons, reasoner, wired),
        "pillars": {
            "digital": {"obs": st["by_source"].get("mac_screen", 0),
                        "state": "live" if daemons["screen_daemon"] else "down"},
            "physical": {"obs": st["by_source"].get("phys_video", 0), "state": "offline-verified"},
        },
        "reasoner_pct": reasoner["pct"],            # None => UNMEASURED, never a hardcoded guess
        "reasoner_state": reasoner["state"],
        "reasoner_halluc_pct": reasoner["halluc_pct"],
        "reasoner_wired_live": wired,
        "pitch_day": "2026-07-01",
        "honesty_floor": "<10% confident-wrong (sacred)",
    }
    try:  # preserve the Scribe's narration across Metrics rewrites
        state["narration"] = json.loads(STATE.read_text()).get("narration", "")
    except Exception:  # noqa: BLE001
        state["narration"] = ""
    STATE.write_text(json.dumps(state, indent=2))
    _set("Metrics", status="idle", task="", last=f"{st['total']} nodes, {st['obs_per_min']}/min")


def _read_reasoner_eval() -> dict:
    """Reasoner accuracy is a MEASUREMENT or it is UNMEASURED. Reads the real store-eval
    artifact (evaluation/ras/store_eval.json, written by the annotate-live scorer, T4).
    NO hardcoded fallback — a missing eval yields UNMEASURED, not a flattering 80."""
    try:
        data = json.loads((ROOT / "evaluation" / "ras" / "store_eval.json").read_text())
        return {"state": "measured", "pct": int(data.get("answered_pct", 0)),
                "halluc_pct": float(data.get("halluc_pct", 100.0)), "n": int(data.get("n", 0))}
    except Exception:  # noqa: BLE001
        return {"state": "UNMEASURED", "pct": None, "halluc_pct": None, "n": 0}


def _mechanical_overall(st: dict, daemons: dict, reasoner: dict, wired: bool) -> int:
    """Overall progress from REAL signals only (store, process table, eval, wiring flag) —
    never an average of LLM-authored pillar guesses. It cannot rise on narration alone."""
    pts = 0
    if daemons.get("screen_daemon"):
        pts += 15
    total = int(st.get("total", 0) or 0)
    if total > 0:
        pts += 10
    if total >= 300:
        pts += 5
    if wired:
        pts += 25                                   # store reasoner IS the live /ask path
    if reasoner.get("state") == "measured":
        pts += 10
        pct = reasoner.get("pct") or 0
        halluc = reasoner.get("halluc_pct")
        halluc = 100.0 if halluc is None else halluc
        if pct >= 75 and halluc < 10:
            pts += 20
        elif pct >= 40:
            pts += 10
    if int(st.get("by_source", {}).get("phone_camera", 0) or 0) > 0:
        pts += 15                                   # live ON-DEVICE physical (not video replay)
    return min(pts, 100)


# ---- AGENT: Perceiver (gemma vision) — backfills physical obs --------------------
_perc_cursor = {"vid": 0, "t": 0.0}  # which walk video + time offset


def run_perceiver() -> None:
    if not WALKS:
        _set("Perceiver", status="idle", last="no walk videos")
        return
    import cv2  # type: ignore
    from mac_vision_perceive import perceive_frame_b64
    from trace_memory.store import TraceMemoryStore

    vid = WALKS[_perc_cursor["vid"] % len(WALKS)]
    name = Path(vid).name
    cap = cv2.VideoCapture(vid)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    start_t = _perc_cursor["t"]
    if start_t >= dur:  # exhausted -> rotate to next video
        cap.release()
        _perc_cursor["vid"] += 1
        _perc_cursor["t"] = 0.0
        _set("Perceiver", status="idle", last=f"finished {name}, rotating")
        _activity("Perceiver", "rotated", f"{name} exhausted")
        return
    _set("Perceiver", status="working", task=f"perceive {name} @ {start_t:.0f}s", started=_now())
    store = TraceMemoryStore(STORE)
    kept = 0
    t = start_t
    base = int(time.time() * 1000)
    with GPU:
        for _ in range(3):  # a few frames per cycle -> visible, steady progress
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            import cv2 as _cv
            sharp = float(_cv.Laplacian(_cv.cvtColor(frame, _cv.COLOR_BGR2GRAY), _cv.CV_64F).var())
            if sharp >= 80:
                ok2, buf = _cv.imencode(".jpg", frame, [_cv.IMWRITE_JPEG_QUALITY, 92])
                if ok2:
                    b64 = base64.b64encode(buf.tobytes()).decode()
                    del frame, buf
                    try:
                        desc = perceive_frame_b64(b64)
                    except Exception as e:  # noqa: BLE001
                        desc = ""
                        _activity("Perceiver", "error", str(e))
                    del b64
                    if desc.strip():
                        store.write_observation(
                            text=f"PHYS [{name} @ {t:.1f}s]\n{desc}",
                            t_ms=base + int(t * 1000), source="phys_video",
                            place=f"video:{name}",
                            provenance={"channel": "phys_video_gemma", "video": name,
                                        "frame_time_s": round(t, 2), "sharpness": round(sharp, 1)},
                            metadata={"video": name, "frame_time_s": round(t, 2), "agent": "Perceiver"})
                        kept += 1
                        _set("Perceiver", status="working", task=f"{name} @ {t:.0f}s: "
                             + desc.replace(chr(10), " ")[:60])
            t += 3.0
    cap.release()
    store.close()
    _perc_cursor["t"] = t
    with _LOCK:
        _AGENTS["Perceiver"]["done"] += kept
    _set("Perceiver", status="idle", task="", last=f"+{kept} phys obs from {name} @ {t:.0f}s")
    _activity("Perceiver", "perceived", f"+{kept} physical obs from {name} up to {t:.0f}s")


# ---- AGENT: Evaluator (gemma) — answerability over the store ---------------------
_EVAL_QS = ["What laptop did I use?", "Was there a shopping cart?", "What was on a screen I looked at?",
            "Did I see a backpack?", "What brand names were visible?"]
_eval_i = {"i": 0}


def run_evaluator() -> None:
    q = _EVAL_QS[_eval_i["i"] % len(_EVAL_QS)]
    _eval_i["i"] += 1
    _set("Evaluator", status="working", task=f"eval: {q}", started=_now())
    try:
        c = sqlite3.connect(STORE)
        rows = [r[0] for r in c.execute(
            "SELECT text FROM memory_nodes WHERE source='phys_video' ORDER BY seq DESC LIMIT 8")]
        c.close()
        ctx = "\n---\n".join(rows)[:3000]
        with GPU:
            ans = _gen("gemma3:12b-it-qat",
                       "Answer ONLY from these observations; if absent, say 'not seen'. Be terse.\n\n"
                       f"OBS:\n{ctx}\n\nQ: {q}\nA:", timeout=45)
        answered = "not seen" not in ans.lower() and len(ans) > 2
        _set("Evaluator", status="idle", task="", last=f"{'ANS' if answered else 'refuse'}: {ans[:50]}")
        _activity("Evaluator", "answered" if answered else "refused", f"{q} -> {ans[:80]}")
        with _LOCK:
            _AGENTS["Evaluator"]["done"] += 1
    except Exception as e:  # noqa: BLE001
        _set("Evaluator", status="idle", last=f"err {e}")


# ---- AGENT: Planner (gemma 27b) — refresh progress from real signals -------------
def run_planner() -> None:
    _set("Planner", status="working", task="refresh plan progress", started=_now())
    try:
        plan = json.loads(PLAN.read_text())
        st = _store_stats()
        # Deterministic, honest nudges from real signals (not gemma guesswork):
        for pil in plan["pillars"]:
            if pil["key"] == "capture":
                phys = st["by_source"].get("phys_video", 0)
                for f in pil["features"]:
                    if f["key"] == "physical_offline":
                        f["progress"] = min(90, 60 + phys // 5)  # climbs as obs accumulate
        plan["today"] = time.strftime("%Y-%m-%d")
        PLAN.write_text(json.dumps(plan, indent=2))
        with _LOCK:
            _AGENTS["Planner"]["done"] += 1
        _set("Planner", status="idle", task="", last=f"plan refreshed (phys={st['by_source'].get('phys_video',0)})")
        _activity("Planner", "refreshed", "progress nudged from store signals")
    except Exception as e:  # noqa: BLE001
        _set("Planner", status="idle", last=f"err {e}")


# ---- AGENT: Scribe (gemma) — honest narration -----------------------------------
def run_scribe() -> None:
    _set("Scribe", status="working", task="write status line", started=_now())
    try:
        st = json.loads(STATE.read_text()) if STATE.exists() else {}
        facts = (f"nodes={st.get('store',{}).get('total')}, "
                 f"obs/min={st.get('store',{}).get('obs_per_min')}, "
                 f"overall={st.get('overall_progress')}%, reasoner~{st.get('reasoner_pct')}%")
        with GPU:
            line = _gen("gemma3:12b-it-qat",
                        "One honest sentence (<=20 words), no hype, only these facts, for a founder "
                        f"glance at sprint progress. FACTS: {facts}\nSENTENCE:", timeout=30)
        st["narration"] = line
        STATE.write_text(json.dumps(st, indent=2))
        with _LOCK:
            _AGENTS["Scribe"]["done"] += 1
        _set("Scribe", status="idle", task="", last=line[:60])
        _activity("Scribe", "narrated", line)
    except Exception as e:  # noqa: BLE001
        _set("Scribe", status="idle", last=f"err {e}")


# ---- scheduler ------------------------------------------------------------------
JOBS = [
    ("Metrics", run_metrics, 5, False),
    ("Perceiver", run_perceiver, 8, True),
    ("Evaluator", run_evaluator, 70, True),
    ("Scribe", run_scribe, 110, True),
    ("Planner", run_planner, 160, True),
]


def main() -> int:
    COCK.mkdir(parents=True, exist_ok=True)
    _log(f"orchestrator up. store={STORE} walks={len(WALKS)} agents={list(_AGENTS)}")
    last = {name: 0.0 for name, *_ in JOBS}
    gpu_worker: threading.Thread | None = None
    while True:
        now = time.time()
        # non-GPU jobs run inline every tick when due (truly parallel to the GPU agent)
        for name, fn, cadence, is_gpu in JOBS:
            if is_gpu or now - last[name] < cadence:
                continue
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                _log(f"{name} err: {e}")
            last[name] = now
        # GPU jobs share one mutex -> launch only the MOST-OVERDUE due job per free slot,
        # so the fast Perceiver never starves Evaluator/Scribe/Planner.
        if not (gpu_worker and gpu_worker.is_alive()):
            due = [(name, fn) for name, fn, cad, gpu in JOBS
                   if gpu and now - last[name] >= cad]
            if due:
                cad_map = {name: cad for name, fn, cad, gpu in JOBS}
                name, fn = max(due, key=lambda nf: (now - last[nf[0]]) / cad_map[nf[0]])

                def _run(f=fn, n=name):
                    try:
                        f()
                    except Exception as e:  # noqa: BLE001
                        _log(f"{n} err: {e}")
                gpu_worker = threading.Thread(target=_run, daemon=True)
                gpu_worker.start()
                last[name] = now
        _flush_agents()
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
