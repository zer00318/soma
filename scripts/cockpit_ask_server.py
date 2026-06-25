#!/usr/bin/env python3
"""TRACE layman cockpit — a tiny stdlib HTTP server that lets a non-technical
stranger try the product: ask anything you looked at, get a plain answer with an
HONESTY badge (saw it / not sure). No new dependencies — plain http.server.

  .venv/bin/python scripts/cockpit_ask_server.py

It serves:
  GET  /                 -> scripts/cockpit_layman.html (the page)
  GET  /api/status       -> {engine_on, things_remembered, mode, capture, last_capture}
  POST /api/ask {question} -> {answer, honesty}   honesty in {saw_it, unsure}
  GET  /api/suggestions  -> 6 good demo questions
  POST /api/feedback     -> append a line to ops/cockpit/feedback.jsonl

Memory is resolved on each request: the live phone keyframe memory wins when it
exists and has records, otherwise the founder-walk demo memory is built from
/tmp/ocr_memory.json, exactly like evaluation/real_brain_probe.build_kf().
ask_home is imported and called over the active memory path — never edited here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

# ask_home is the brain; import defensively so the page still serves if it can't load.
try:
    import ask_home  # noqa: E402
except Exception as e:  # pragma: no cover
    ask_home = None
    print(f"[warn] could not import ask_home: {e!r}")

# On-device PII redaction applied at the storage seam (what we persist is scrubbed).
try:
    from scrub_pii import scrub_pii  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"[warn] could not import scrub_pii: {e!r}")

    def scrub_pii(text, *, mask="[redacted]"):  # type: ignore  fail-open to never break the page
        return text

PHONE_CAPTURES_ROOT = ROOT / "data" / "phone_captures"
LIVE_MEM = PHONE_CAPTURES_ROOT / "live" / "kf_memory.json"
OCR_MEMO = Path("/tmp/ocr_memory.json")
MODEL = "gemma3:12b-it-qat"
OLLAMA = "http://127.0.0.1:11434"
ASK_TIMEOUT = 60
PAGE = ROOT / "scripts" / "cockpit_layman.html"
ENGINE_PAGE = ROOT / "ops" / "cockpit" / "cockpit_engine.html"
OPS_PAGE = ROOT / "ops" / "cockpit" / "cockpit_ops.html"
ENGINE_JSON = ROOT / "ops" / "cockpit" / "engine.json"
AGENT_PLAN_JSON = ROOT / "ops" / "cockpit" / "agent_plan.json"
ACTIVITY_LOG = ROOT / "ops" / "cockpit" / "activity.jsonl"   # the flight recorder
FEEDBACK = ROOT / "ops" / "cockpit" / "feedback.jsonl"
ABLATION = ROOT / "evaluation" / "ras" / "posthoc_ablation_n16.json"
DEMO_ASK_CACHE = ROOT / "ops" / "cockpit" / "demo_cache.json"
LIVE44_DAY_STATUS = ROOT / "ops" / "cockpit" / "eval_live44_day.json"
LIVE44_WALK_STATUS = ROOT / "ops" / "cockpit" / "eval_live44_walk.json"
LIVE44_SUMMARY = ROOT / "evaluation" / "ras" / "live44_summary.json"
SCENE_EVAL_LATEST = ROOT / "evaluation" / "results" / "scene_eval_latest.json"
CODEX_QUEUE = ROOT / "ops" / "codex_queue"
CODEX_DRIVER_LOG = CODEX_QUEUE / "driver.log"

try:
    import cockpit_engine  # noqa: E402
except Exception as e:  # pragma: no cover
    cockpit_engine = None
    print(f"[warn] could not import cockpit_engine: {e!r}")

try:
    from trace_memory.adapters.sqlite_eventlog import SqliteEventLog  # noqa: E402
    from trace_memory.application.entity_binder import bind_entities  # noqa: E402
except Exception as e:  # pragma: no cover
    SqliteEventLog = None
    bind_entities = None
    print(f"[warn] could not import trace_memory eventlog/binder: {e!r}")

# The active memory path is resolved per request. Parsed counts are cached by
# file signature so status polling stays cheap while live capture is idle.
_MEM_LOCK = threading.Lock()
_LIVE_CACHE = {}
_DEMO_CACHE = {}
_EVENT_CACHE = {}
_DEMO_ASK_CACHE_SNAPSHOT = (None, {})
_ASK_LOCK = threading.Lock()


def _git(*args):
    try:
        return subprocess.check_output(
            ("git",) + args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


def _live_git_state():
    return {
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "head": _git("log", "-1", "--pretty=%h %s") or "unknown",
        "ahead_of_main": _git("rev-list", "--count", "main..HEAD") or "?",
        "dirty_files": len(
            [x for x in _git("status", "--porcelain=v1").splitlines() if x]
        ),
    }


def _engine_snapshot():
    try:
        with ENGINE_JSON.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {"error": "engine.json not found"}
    if isinstance(data, dict):
        if not isinstance(data.get("pipeline"), list):
            data["pipeline"] = _engine_pipeline_defaults()
        if not isinstance(data.get("deliverables"), list):
            data["deliverables"] = _engine_deliverable_defaults()
        now = int(time.time())
        data["server_ts"] = now
        data["git"] = _live_git_state()
        data["runtime"] = {
            "memory": active_memory(),
            "ollama_up": ollama_up(),
            "brain_model": MODEL,
            "ask_timeout_s": ASK_TIMEOUT,
        }
        data["measurement_runtime"] = _live44_snapshot(now)
    return data


def _read_json_file(path, default):
    try:
        with Path(path).open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _command_output(*args, timeout=4):
    try:
        return subprocess.check_output(
            args,
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).strip()
    except Exception:
        return ""


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _engine_pipeline_defaults():
    if cockpit_engine is None:
        return []
    try:
        return cockpit_engine.pipeline()
    except Exception:
        return []


def _engine_deliverable_defaults():
    if cockpit_engine is None:
        return []
    try:
        return cockpit_engine.deliverables()
    except Exception:
        return []


def _parse_ps_rows(text):
    rows = []
    for line in (text or "").splitlines():
        m = re.match(r"^\s*(\d+)\s+([0-9.]+)\s+(\S+)\s+(.*)$", line)
        if not m:
            continue
        rows.append(
            {
                "pid": int(m.group(1)),
                "cpu_pct": _safe_float(m.group(2)),
                "elapsed": m.group(3),
                "command": m.group(4).strip(),
            }
        )
    return rows


def _job_process_snapshot(pattern):
    pids = []
    raw = _command_output("pgrep", "-f", str(pattern or ""), timeout=3)
    for line in raw.splitlines():
        pid = _safe_int(line.strip(), default=None)
        if pid:
            pids.append(pid)
    if not pids:
        return {
            "state": "DEAD",
            "alive": False,
            "pid": None,
            "pid_count": 0,
            "elapsed": "—",
            "cpu_pct": None,
            "command": "",
            "pids": [],
        }

    rows = _parse_ps_rows(
        _command_output(
            "ps",
            "-p",
            ",".join(str(pid) for pid in pids),
            "-o",
            "pid=",
            "-o",
            "%cpu=",
            "-o",
            "etime=",
            "-o",
            "command=",
            timeout=4,
        )
    )
    if not rows:
        return {
            "state": "ALIVE",
            "alive": True,
            "pid": pids[0],
            "pid_count": len(pids),
            "elapsed": "—",
            "cpu_pct": None,
            "command": "",
            "pids": pids,
        }

    rows.sort(key=lambda row: (row["cpu_pct"], row["pid"]), reverse=True)
    primary = rows[0]
    return {
        "state": "ALIVE",
        "alive": True,
        "pid": primary["pid"],
        "pid_count": len(rows),
        "elapsed": primary["elapsed"] or "—",
        "cpu_pct": primary["cpu_pct"],
        "command": primary["command"],
        "pids": [row["pid"] for row in rows],
    }


def _progress_label(path, raw):
    label = ""
    if isinstance(raw, dict):
        label = str(raw.get("label") or raw.get("name") or "").strip()
    if label:
        return label
    stem = Path(path).stem
    stem = re.sub(r"^eval_live44_", "", stem)
    return stem.replace("_", " ")


def _progress_snapshot(path):
    raw = _read_json_file(path, {})
    label = _progress_label(path, raw)
    if not isinstance(raw, dict) or not raw:
        return {
            "path": str(path),
            "label": label,
            "state": "unknown",
            "done": None,
            "total": None,
            "correct": None,
            "wrong": None,
            "miss": None,
            "summary": f"{label} —",
        }

    state = str(raw.get("state") or "unknown")
    done = _safe_int(raw.get("done"), 0)
    total = _safe_int(raw.get("total"), 0)
    correct = _safe_int(raw.get("correct"), 0)
    wrong = _safe_int(raw.get("wrong"), 0)
    miss = _safe_int(raw.get("miss"), 0)

    done_word = "done" if state in ("done", "complete", "completed") else state
    total_text = str(total) if total else "?"
    summary = (
        f"{label} {done}/{total_text} {done_word} "
        f"({correct}✔ {wrong}✘ {miss}–)"
    ).strip()
    current_q = raw.get("current_q")
    if current_q not in (None, "") and total and done < total:
        summary += f"  q {current_q}"

    return {
        "path": str(path),
        "label": label,
        "state": state,
        "done": done,
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "miss": miss,
        "current_q": current_q,
        "summary": summary,
    }


def _jobs_snapshot(plan_doc):
    jobs = []
    raw_jobs = plan_doc.get("jobs") if isinstance(plan_doc, dict) else []
    for job in raw_jobs if isinstance(raw_jobs, list) else []:
        if not isinstance(job, dict):
            continue
        pattern = str(job.get("pattern") or "").strip()
        progress_paths = job.get("progress") if isinstance(job.get("progress"), list) else []
        progress = [_progress_snapshot(ROOT / str(path)) for path in progress_paths]
        proc = _job_process_snapshot(pattern) if pattern else {
            "state": "DEAD",
            "alive": False,
            "pid": None,
            "pid_count": 0,
            "elapsed": "—",
            "cpu_pct": None,
            "command": "",
            "pids": [],
        }
        jobs.append(
            {
                "label": str(job.get("label") or pattern or "job"),
                "pattern": pattern,
                "does": str(job.get("does") or "—"),
                "state": proc["state"],
                "alive": proc["alive"],
                "pid": proc["pid"],
                "pid_count": proc["pid_count"],
                "elapsed": proc["elapsed"],
                "cpu_pct": proc["cpu_pct"],
                "command": proc["command"],
                "pids": proc["pids"],
                "progress_items": progress,
                "progress_compact": "  ".join(
                    item["summary"] for item in progress if item.get("summary")
                ) or "—",
            }
        )
    return jobs


def _parse_load_averages(text):
    m = re.search(
        r"load averages?:\s*([0-9.]+)[,\s]+([0-9.]+)[,\s]+([0-9.]+)",
        text or "",
        flags=re.I,
    )
    if m:
        return [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    try:
        return [round(x, 2) for x in os.getloadavg()]
    except Exception:
        return []


def _ollama_runtime():
    raw = _command_output("ollama", "ps", timeout=5)
    if not raw:
        return {"state": "idle", "model": None, "processor": None, "raw": ""}
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return {"state": "idle", "model": None, "processor": None, "raw": raw}
    lower = " ".join(lines).lower()
    if "no models loaded" in lower or len(lines) == 1:
        return {"state": "idle", "model": None, "processor": None, "raw": raw}
    first = lines[1] if lines[0].lower().startswith("name") else lines[0]
    cols = re.split(r"\s{2,}", first)
    model = cols[0] if cols else None
    processor = cols[3] if len(cols) >= 4 else None
    return {
        "state": "loaded",
        "model": model,
        "processor": processor,
        "raw": first,
    }


def _top_cpu_process():
    rows = _parse_ps_rows(
        _command_output(
            "ps",
            "-Ao",
            "pid=",
            "-o",
            "%cpu=",
            "-o",
            "etime=",
            "-o",
            "command=",
            timeout=5,
        )
    )
    if not rows:
        return {"pid": None, "cpu_pct": None, "elapsed": "—", "command": "unknown"}
    rows.sort(key=lambda row: row["cpu_pct"], reverse=True)
    return rows[0]


def _machine_snapshot():
    uptime_raw = _command_output("uptime", timeout=3)
    return {
        "uptime_raw": uptime_raw,
        "load_avg": _parse_load_averages(uptime_raw),
        "ollama": _ollama_runtime(),
        "top_cpu": _top_cpu_process(),
    }


def _normalize_plan_steps(plan_doc):
    items = plan_doc.get("plan") if isinstance(plan_doc, dict) else []
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            out.append({"step": item, "state": "unknown", "note": ""})
            continue
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "step": str(item.get("step") or item.get("title") or "—"),
                "state": str(item.get("state") or "unknown"),
                "note": str(item.get("note") or ""),
            }
        )
    return out


def _blocked_on_founder(plan_doc):
    raw = plan_doc.get("blocked_on_founder") if isinstance(plan_doc, dict) else []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw] if isinstance(raw, list) else []


def _overall_status(plan_doc, jobs, plan_steps):
    raw = str(plan_doc.get("status") or "").strip().lower() if isinstance(plan_doc, dict) else ""
    if raw in ("working", "blocked", "idle"):
        return raw
    if any(step.get("state") == "blocked" for step in plan_steps) or _blocked_on_founder(plan_doc):
        return "blocked"
    if any(job.get("alive") for job in jobs) or any(step.get("state") == "now" for step in plan_steps):
        return "working"
    return "idle"


def _activity_snapshot(limit=60):
    """The flight recorder: newest-first timestamped events the Chief logs as it works.
    Each line of activity.jsonl is {"ts": <epoch>, "kind": <str>, "text": <str>}. Robust to
    malformed lines (a half-written append never breaks the page)."""
    events = []
    try:
        if ACTIVITY_LOG.exists():
            with ACTIVITY_LOG.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    events.append({
                        "ts": _safe_int(rec.get("ts"), 0),
                        "kind": str(rec.get("kind") or "info"),
                        "text": str(rec.get("text") or ""),
                    })
    except Exception:
        pass
    events.sort(key=lambda e: e["ts"], reverse=True)
    return events[:limit]


def _latest_scene_eval_number():
    raw = _read_json_file(SCENE_EVAL_LATEST, {})
    summary = raw.get("summary") if isinstance(raw, dict) else {}
    if not isinstance(summary, dict) or not summary:
        return {}
    return {
        "n": _safe_int(summary.get("n"), 0),
        "correct_pct": _safe_float(summary.get("correct_pct"), 0.0),
        "correct_ci_95": summary.get("correct_ci_95") or {},
        "hallucination_pct": _safe_float(summary.get("hallucination_pct"), 0.0),
        "hallucination_ci_95": summary.get("hallucination_ci_95") or {},
        "source": str(SCENE_EVAL_LATEST.relative_to(ROOT)),
        "note": "FIXTURE ONLY — scene_eval_latest.json is not the real-capture product number.",
        "generated_at": raw.get("generated_at"),
    }


def _queue_pending_count():
    pending = CODEX_QUEUE / "pending"
    try:
        return len([path for path in pending.glob("*.md") if path.is_file()])
    except Exception:
        return 0


def _last_committed_task():
    try:
        lines = CODEX_DRIVER_LOG.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    for line in reversed(lines):
        match = re.search(r"\bcommitted\s+([^\s]+)\s+\(", line)
        if match:
            return match.group(1)
    return ""


def _queue_runtime_snapshot():
    return {
        "driver_alive": bool(_command_output("pgrep", "-f", "scripts/codex_loop.sh", timeout=3)),
        "codex_active": bool(_command_output("pgrep", "-f", "codex exec", timeout=3)),
        "queue_pending": _queue_pending_count(),
        "last_committed_task": _last_committed_task(),
    }


def _agent_plan_snapshot():
    plan_doc = _read_json_file(AGENT_PLAN_JSON, {})
    if not isinstance(plan_doc, dict):
        plan_doc = {}
    plan_doc = dict(plan_doc)
    honest_number = _latest_scene_eval_number()
    if honest_number:
        plan_doc["honest_number"] = honest_number
    plan_doc["running"] = _queue_runtime_snapshot()
    return plan_doc


def _ops_snapshot():
    now = int(time.time())
    plan_doc = _agent_plan_snapshot()
    engine_doc = _engine_snapshot()

    plan_steps = _normalize_plan_steps(plan_doc)
    jobs = _jobs_snapshot(plan_doc)
    blocked = _blocked_on_founder(plan_doc)
    headline_block = engine_doc.get("headline") if isinstance(engine_doc.get("headline"), dict) else {}
    official = engine_doc.get("official_measurement") if isinstance(engine_doc.get("official_measurement"), dict) else {}
    progress = {
        "honest_number": {
            "status": str(official.get("status") or "UNMEASURED"),
            "headline": str(
                official.get("headline")
                or headline_block.get("verdict")
                or "—"
            ),
            "why": str(official.get("why") or "—"),
            "nearest_proxy": str(official.get("nearest_proxy") or "—"),
            "proxy_state": str(
                (engine_doc.get("measurement_runtime") or {}).get("state") or "unknown"
            ),
        },
        "pipeline": engine_doc.get("pipeline") if isinstance(engine_doc.get("pipeline"), list) else _engine_pipeline_defaults(),
        "deliverables": engine_doc.get("deliverables") if isinstance(engine_doc.get("deliverables"), list) else _engine_deliverable_defaults(),
        "measurement_runtime": engine_doc.get("measurement_runtime") if isinstance(engine_doc.get("measurement_runtime"), dict) else {},
        "engine_url": "/engine",
    }

    return {
        "server_ts": now,
        "status": _overall_status(plan_doc, jobs, plan_steps),
        "headline": str(
            plan_doc.get("headline")
            or headline_block.get("verdict")
            or headline_block.get("title")
            or "mission control unavailable"
        ),
        "sources": {
            "agent_plan": "ok" if AGENT_PLAN_JSON.exists() else "missing",
            "engine": "ok" if ENGINE_JSON.exists() else "missing",
        },
        "jobs": jobs,
        "activity": _activity_snapshot(),
        # machine load deliberately NOT surfaced — the founder reads CPU/RAM from Activity
        # Monitor; the cockpit shows PRODUCT + AGENT telemetry, not the box.
        "chief": {
            "doing_now": str(plan_doc.get("doing_now") or "—"),
            "current_task": str(plan_doc.get("current_task") or "—"),
            "next_action": str(plan_doc.get("next_action") or "—"),
            "next_wake": str(plan_doc.get("next_wake") or "—"),
        },
        "plan": plan_steps,
        "blocked_on_founder": blocked,
        "progress": progress,
        "agent_plan": plan_doc,
        "engine": engine_doc,
    }


def _ops_page_html():
    try:
        template = OPS_PAGE.read_text(encoding="utf-8")
    except Exception:
        template = (
            "<!doctype html><meta charset='utf-8'>"
            "<title>TRACE Ops</title><body>ops page unavailable</body>"
        )
    bootstrap = json.dumps(_ops_snapshot(), ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__OPS_BOOTSTRAP__", bootstrap)


def _clip_eval_snapshot(label, path, total_hint, now):
    raw = _read_json_file(path, {})
    if not isinstance(raw, dict) or not raw:
        return {
            "label": label,
            "state": "not_started",
            "done": 0,
            "total": total_hint,
            "correct": 0,
            "wrong": 0,
            "miss": 0,
            "needs_review": 0,
            "hard_ras": None,
            "halluc_pct": None,
            "updated_epoch": None,
            "age_s": None,
            "current_question": None,
            "eta_human": None,
            "stalled": False,
            "note": "no score file yet",
        }
    updated = raw.get("updated_epoch")
    age_s = max(0, now - int(updated)) if updated else None
    avg_s = float(raw.get("avg_s_per_q") or 0.0)
    stale_after = max(180, int(avg_s * 4)) if avg_s else 240
    stalled = bool(raw.get("state") == "running" and age_s is not None and age_s > stale_after)
    state = raw.get("state") or "unknown"
    if stalled:
        state = "stalled"
    return {
        "label": label,
        "state": state,
        "done": int(raw.get("done", 0) or 0),
        "total": int(raw.get("total", 0) or total_hint),
        "correct": int(raw.get("correct", 0) or 0),
        "wrong": int(raw.get("wrong", 0) or 0),
        "miss": int(raw.get("miss", 0) or 0),
        "needs_review": int(raw.get("needs_review", 0) or 0),
        "hard_ras": raw.get("hard_ras"),
        "halluc_pct": raw.get("halluc_pct"),
        "updated_epoch": updated,
        "age_s": age_s,
        "current_q": raw.get("current_q"),
        "current_question": raw.get("current_question"),
        "eta_human": raw.get("eta_human"),
        "stalled": stalled,
        "note": raw.get("message") or "",
    }


def _live44_snapshot(now):
    day = _clip_eval_snapshot("day", LIVE44_DAY_STATUS, 19, now)
    walk = _clip_eval_snapshot("walk", LIVE44_WALK_STATUS, 25, now)
    summary_doc = _read_json_file(LIVE44_SUMMARY, {})
    summary = summary_doc.get("summary") if isinstance(summary_doc, dict) else None

    states = {day["state"], walk["state"]}
    if "running" in states:
        overall = "running"
    elif "stalled" in states:
        overall = "stalled"
    elif "paused" in states:
        overall = "paused"
    elif states == {"complete"}:
        overall = "complete"
    elif day["done"] or walk["done"]:
        overall = "partial"
    else:
        overall = "not_started"

    return {
        "battery_name": "live44",
        "question_total": 44,
        "clips": [day, walk],
        "summary": summary,
        "state": overall,
    }


def _secs(name):
    m = re.search(r"_(\d+\.\d+)s", name)
    return float(m.group(1)) if m else 0.0


def _file_sig(path):
    """Return a cheap freshness signature for a usable non-empty file."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    if st.st_size <= 0:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_mtime)


def _event_db_paths(captures_root=None):
    captures_root = captures_root or PHONE_CAPTURES_ROOT
    try:
        return sorted(
            (path for path in Path(captures_root).glob("*/events.db") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []


def _event_db_snapshot(path):
    sig = _file_sig(path)
    if sig is None or SqliteEventLog is None:
        return None

    cache_key = (str(path), sig)
    with _MEM_LOCK:
        cached = dict(_EVENT_CACHE) if _EVENT_CACHE.get("key") == cache_key else None

    if cached is None:
        try:
            log = SqliteEventLog(str(path))
            try:
                observations = tuple(log.observations())
            finally:
                log.close()
        except Exception:
            return None

        object_observations = [
            observation
            for observation in observations
            if getattr(observation, "kind", "").strip().lower() == "object"
        ]
        subject_labels = {
            str(observation.subject).strip().lower()
            for observation in object_observations
            if str(observation.subject).strip()
        }
        entities = []
        if bind_entities is not None and object_observations:
            try:
                entities = bind_entities(object_observations)
            except Exception:
                entities = []

        distinct_subject_count = len(entities) or len(subject_labels)
        bound_entity_count = sum(
            max(1, _safe_int(getattr(entity, "count", 1), 1))
            for entity in entities
        )
        things = bound_entity_count or distinct_subject_count or len(observations)
        cached = {
            "key": cache_key,
            "path": str(path),
            "observation_count": len(observations),
            "object_observation_count": len(object_observations),
            "distinct_subject_count": distinct_subject_count,
            "bound_entity_count": bound_entity_count or distinct_subject_count or len(observations),
            "things_remembered": things,
        }
        with _MEM_LOCK:
            _EVENT_CACHE.clear()
            _EVENT_CACHE.update(cached)

    age = time.time() - sig[2]
    return {
        "path": cached["path"],
        "things_remembered": cached["things_remembered"],
        "observation_count": cached["observation_count"],
        "object_observation_count": cached["object_observation_count"],
        "distinct_subject_count": cached["distinct_subject_count"],
        "bound_entity_count": cached["bound_entity_count"],
        "mode": "live",
        "capture": "LIVE" if age <= 60 else "IDLE",
        "last_capture": (
            "latest event log %s (%d observations, %d bound things, %d subject types)"
            % (
                _age_words(age),
                cached["observation_count"],
                cached["bound_entity_count"],
                cached["distinct_subject_count"],
            )
        ),
    }


def _resolve_live_event_memory():
    for path in _event_db_paths():
        snapshot = _event_db_snapshot(path)
        if snapshot and snapshot.get("observation_count", 0) > 0:
            return snapshot
    return None


def _normalize_question(question):
    return re.sub(r"\s+", " ", str(question).strip().lower())


def _load_demo_ask_cache():
    """Return the mtime-cached instant demo QA map, or {} when unavailable."""
    global _DEMO_ASK_CACHE_SNAPSHOT
    sig = _file_sig(DEMO_ASK_CACHE)
    cached_sig, cached_data = _DEMO_ASK_CACHE_SNAPSHOT
    if sig == cached_sig:
        return cached_data
    if sig is None:
        data = {}
        _DEMO_ASK_CACHE_SNAPSHOT = (None, data)
        return data
    try:
        with DEMO_ASK_CACHE.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    _DEMO_ASK_CACHE_SNAPSHOT = (sig, data)
    return data


def demo_ask_cache_hit(question):
    rec = _load_demo_ask_cache().get(_normalize_question(question))
    if not isinstance(rec, dict):
        return None
    answer = rec.get("answer")
    if not isinstance(answer, str):
        return None
    honesty = rec.get("honesty")
    if honesty not in ("saw_it", "unsure"):
        honesty = "unsure"
    return {
        "answer": answer,
        "honesty": honesty,
        "source": "demo_cache",
        "cached": True,
    }


def _load_kf(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _thing_count(records):
    distinct = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ocr = rec.get("ocr") or []
        if isinstance(ocr, str):
            ocr = [ocr]
        if not isinstance(ocr, list):
            continue
        for line in ocr:
            line = str(line).strip()
            if line:
                distinct.add(line.lower())
    return len(distinct) if distinct else len(records)


def _age_words(seconds):
    seconds = max(0, int(seconds))
    if seconds < 2:
        return "just now"
    if seconds < 60:
        return "%d seconds ago" % seconds
    minutes = seconds // 60
    if minutes < 60:
        return "%d minute%s ago" % (minutes, "" if minutes == 1 else "s")
    hours = minutes // 60
    return "%d hour%s ago" % (hours, "" if hours == 1 else "s")


def _resolve_live_memory():
    sig = _file_sig(LIVE_MEM)
    if sig is None:
        return None

    with _MEM_LOCK:
        cached = dict(_LIVE_CACHE) if _LIVE_CACHE.get("sig") == sig else None

    if cached is None:
        records = _load_kf(LIVE_MEM)
        if not records:
            return None
        cached = {
            "sig": sig,
            "path": str(LIVE_MEM),
            "things": _thing_count(records),
            "records": len(records),
        }
        with _MEM_LOCK:
            _LIVE_CACHE.clear()
            _LIVE_CACHE.update(cached)

    age = time.time() - sig[2]
    return {
        "path": cached["path"],
        "things_remembered": cached["things"],
        "mode": "live",
        "capture": "LIVE" if age <= 60 else "IDLE",
        "last_capture": "last live capture %s (%d records)" %
        (_age_words(age), cached["records"]),
    }


def _build_demo_memory(sig):
    """Build kf_memory.json from cached per-frame OCR (same shape as
    real_brain_probe.build_kf). Returns a demo memory snapshot or None when the
    OCR cache is missing/empty."""
    try:
        with OCR_MEMO.open(encoding="utf-8") as f:
            mem = json.load(f)
    except Exception:
        return None
    recs, distinct = [], set()
    for frame, lines in (mem.items() if isinstance(mem, dict) else []):
        if isinstance(lines, str):
            lines = [lines]
        lines = [str(l).strip() for l in (lines or []) if str(l).strip()]
        # Scrub PII before the OCR becomes stored/served memory — the privacy claim,
        # enforced on the actual artifact the brain reasons over (kf_memory.json below).
        lines = [scrub_pii(line) for line in lines]
        for line in lines:
            distinct.add(line.lower())
        recs.append({"t": _secs(frame), "frame": frame, "caption": "", "ocr": lines})
    if not recs:
        return None
    recs.sort(key=lambda r: r["t"])
    d = Path(tempfile.mkdtemp(prefix="cockpit_walk_"))
    path = d / "kf_memory.json"
    path.write_text(json.dumps(recs, ensure_ascii=False))
    span = recs[-1]["t"] - recs[0]["t"] if len(recs) > 1 else 0.0
    return {
        "sig": sig,
        "path": str(path),
        "things_remembered": len(distinct) if distinct else len(recs),
        "mode": "demo",
        "capture": "IDLE",
        "last_capture": "a %.0f-second past walk (%d frames)" % (span, len(recs)),
    }


def _empty_demo_memory():
    return {
        "path": None,
        "things_remembered": 0,
        "mode": "demo",
        "capture": "IDLE",
        "last_capture": "no capture yet",
    }


def _resolve_demo_memory():
    sig = _file_sig(OCR_MEMO)
    if sig is None:
        return _empty_demo_memory()

    with _MEM_LOCK:
        cached = dict(_DEMO_CACHE) if _DEMO_CACHE.get("sig") == sig else None

    if cached and cached.get("path") and Path(cached["path"]).exists():
        return {k: v for k, v in cached.items() if k != "sig"}

    built = _build_demo_memory(sig)
    if built is None:
        return _empty_demo_memory()
    with _MEM_LOCK:
        _DEMO_CACHE.clear()
        _DEMO_CACHE.update(built)
    return {k: v for k, v in built.items() if k != "sig"}


def active_memory():
    """Return the current active memory snapshot.

    Prefer live phone capture ONLY when it is actually streaming (fresh) or has
    a meaningful amount of memory; otherwise fall back to the rich demo walk so a
    stranger always gets a real experience instead of a near-empty live buffer."""
    live = _resolve_live_memory()
    if live and (live.get("capture") == "LIVE"
                 or live.get("things_remembered", 0) >= 8):
        return live
    demo = _resolve_demo_memory()
    if demo and demo.get("things_remembered", 0) > 0:
        return demo
    return live or demo


def ollama_up():
    """True if the local ollama is reachable (the model server is on)."""
    try:
        with urllib.request.urlopen(OLLAMA.rstrip("/") + "/api/tags", timeout=3) as r:
            json.loads(r.read().decode("utf-8", "replace"))
        return True
    except Exception:
        return False


def _status_snapshot():
    answer_memory = active_memory()
    capture_memory = _resolve_live_event_memory() or answer_memory
    status = {
        "engine_on": bool(ollama_up() and answer_memory.get("path")),
        "things_remembered": _safe_int(capture_memory.get("things_remembered"), 0),
        "mode": capture_memory.get("mode", answer_memory.get("mode", "demo")),
        "capture": capture_memory.get("capture", answer_memory.get("capture", "IDLE")),
        "last_capture": capture_memory.get(
            "last_capture",
            answer_memory.get("last_capture", "no capture yet"),
        ),
    }
    for key in (
        "observation_count",
        "object_observation_count",
        "distinct_subject_count",
        "bound_entity_count",
    ):
        if key in capture_memory:
            status[key] = _safe_int(capture_memory.get(key), 0)
    return status


def load_suggestions():
    """A curated, demo-SAFE set of tappable questions, hand-verified against the
    current brain on the founder-walk memory. The first four are answers it reads
    correctly ('I saw this'); the last is one it honestly declines (cursive it
    can't read) — that refusal is the product's whole point, so it's a feature to
    show, not a bug to hide. (Earlier the chips were pulled from the ablation set
    and surfaced questions the no-anchor brain gets wrong, e.g. 'CHg'.)"""
    # These EXACTLY match the keys in ops/cockpit/demo_cache.json so every tap is a
    # zero-latency, curated, grounded answer (the 3-min pitch flow):
    #   read -> meaning -> verbatim name -> honest refusal -> stand-your-ground.
    return [
        "What years are listed next to Robert Sauer on the lower plaque?",
        "What is the name on the Wilhelm Conrad Röntgen sign?",
        "Who was Wilhelm Conrad Röntgen?",
        "What did Röntgen discover, according to the sign?",
        "What was the wifi password on the wall?",
        "Was the plaque next to the chemical structure dated 1899?",
    ]


def classify_honesty(res):
    """Map an ask_home result to the layman honesty badge.

    'saw_it' when the brain produced a confident, grounded answer (consensus OCR
    or a non-refused assembler answer). 'unsure' when it refused / said it didn't
    read it / has nothing — the whole point: it won't guess."""
    if not res:
        return "unsure"
    ans = (res.get("answer") or "").strip()
    if res.get("refused"):
        return "unsure"
    if not ans:
        return "unsure"
    low = ans.lower()
    unsure_markers = (
        "i don't have that", "i didn't read", "didn't see", "don't have it",
        "couldn't read", "i don't know", "not in memory", "i didn't capture",
        "i don't track", "didn't read enough", "wasn't sure", "not sure",
        "no clear", "i had no", "i had trouble",
    )
    if any(m in low for m in unsure_markers):
        return "unsure"
    return "saw_it"


def do_ask(question):
    """Call the real brain over the active memory with a timeout guard.
    Returns {answer, honesty}. Never raises to the client."""
    if not question or not question.strip():
        return {"answer": "Ask me something you looked at.", "honesty": "unsure"}
    memory = active_memory()
    mem_path = memory.get("path")
    if ask_home is None or mem_path is None:
        return {"answer": "I'm still warming up — no memory loaded yet.",
                "honesty": "unsure"}
    result = {"res": None, "err": None}

    def _run():
        try:
            # ask_with_understanding = ask() + world-knowledge EXPAND for "what/who is
            # this" questions (additive two-zone); falls back to plain ask() otherwise.
            _ask = getattr(ask_home, "ask_with_understanding", ask_home.ask)
            result["res"] = _ask(
                question.strip(), mem_path, model=MODEL, host=OLLAMA,
                timeout=ASK_TIMEOUT)
        except Exception as e:
            result["err"] = e

    # Serialise gemma calls (single GPU) + hard wall-clock guard.
    with _ASK_LOCK:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(ASK_TIMEOUT + 5)
    if t.is_alive():
        return {"answer": "That took too long to recall — try a simpler question.",
                "honesty": "unsure"}
    if result["err"] is not None:
        return {"answer": "I'm still warming up — couldn't reach my memory just now.",
                "honesty": "unsure"}
    res = result["res"] or {}
    ans = (res.get("answer") or "").strip() or \
        "I don't have that in my memory."
    return {"answer": ans, "honesty": classify_honesty(res)}


def append_feedback(payload):
    FEEDBACK.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "epoch": int(time.time()),
        "question": str(payload.get("question", ""))[:500],
        "answer": str(payload.get("answer", ""))[:1000],
        "rating": str(payload.get("rating", ""))[:20],
        "comment": str(payload.get("comment", ""))[:2000],
    }
    with open(FEEDBACK, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


# --------------------------------------------------------------------------- #
# HTTP handler.
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "TRACECockpit/1.0"

    def log_message(self, fmt, *args):  # quieter, one-line
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path):
        try:
            body = Path(path).read_bytes()
        except Exception:
            self._json({"error": "page not found"}, 404)
            return
        self._html_bytes(body)

    def _html_bytes(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html_text(self, text):
        self._html_bytes(text.encode("utf-8"))

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._html(PAGE)
        elif path in ("/ops", "/ops/", "/cockpit_ops.html",
                      "/ops/cockpit/cockpit_ops.html"):
            self._html_text(_ops_page_html())
        elif path == "/ops.json":
            self._json(_ops_snapshot())
        elif path in ("/engine", "/engine/", "/cockpit_engine.html",
                      "/ops/cockpit/cockpit_engine.html"):
            self._html(ENGINE_PAGE)
        elif path in ("/engine.json", "/ops/cockpit/engine.json"):
            self._json(_engine_snapshot())
        elif path == "/api/status":
            self._json(_status_snapshot())
        elif path == "/api/suggestions":
            self._json(load_suggestions())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/ask":
            body = self._read_body()
            question = body.get("question", "")
            cached = demo_ask_cache_hit(question)
            if cached is not None:
                self._json(cached)
                return
            self._json(do_ask(question))
        elif path == "/api/feedback":
            body = self._read_body()
            append_feedback(body)
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)


def pick_port():
    """Try 8799, then 8800. Bind to 0.0.0.0 so a phone on the LAN can reach it."""
    import socket
    for port in (8799, 8800):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            s.close()
            return port
        except OSError:
            s.close()
            continue
    return 8801


def lan_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    port = pick_port()
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ip = lan_ip()
    print("=" * 60)
    print(" TRACE layman cockpit is live")
    print("  local:   http://127.0.0.1:%d/" % port)
    print("  founder ops: http://127.0.0.1:%d/ops" % port)
    print("  LAN/phone: http://%s:%d/" % (ip, port))
    print("  memory:  resolves per request (live: %s)" % LIVE_MEM)
    print("  ollama:  %s" % ("ON" if ollama_up() else "OFF"))
    print("=" * 60, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
