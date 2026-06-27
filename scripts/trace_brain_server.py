#!/usr/bin/env python3
"""TRACE brain endpoint — the Mac-side "ask anything" service the phone calls.

The native iPhone app perceives on-device (FastVLM caption + Vision OCR + YOLO +
speech), keeps ONLY derived text, and never writes raw media. It POSTs that
derived text here; the Mac brain (``ask_home``: gemma3 + specialists + grounding
and honest-refusal gates) answers questions with timestamped citations. When the
local brain honestly refuses or stalls on a hard chain, an OPT-IN frontier
text-egress fallback answers from the SAME derived text — only text ever leaves,
never a pixel. That keeps the no-raw-media moat intact end to end.

Endpoints (HTTP over the LAN so the phone can reach it at http://<mac-ip>:8765):
    GET  /health                      -> {ok, model, frontier}
    POST /ingest  {moment_id, records}-> write kf_memory.json, return counts
    POST /ask     {moment_id, question, allow_frontier, records?}
                                       -> {answer, citations, source, refused}
    GET  /proof?moment_id=...          -> raw-media audit (proves 0 raw files)

records: [{"t": <seconds>, "text": "<OBJECT|.. or EVENT|.. line>",
           "ocr": ["verbatim text", ...]?, "source": "native_vision"?}]

Run with the venv python (needs a local Ollama up):
    TRACE_BRAIN_PORT=8765 .venv/bin/python scripts/trace_brain_server.py
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import ask_home  # noqa: E402  (the brain)
import brain_memory  # noqa: E402  persistent cross-session memory
from scrub_pii import scrub_record  # noqa: E402  on-device PII redaction at the storage seam
from trace_memory.adapters.live_eventlog import (  # noqa: E402
    answer_question as eventlog_answer,
    append_perception_observations,
)

PORT = int(os.environ.get("TRACE_BRAIN_PORT") or os.environ.get("PORT") or "8765")
MODEL = os.environ.get("TRACE_BRAIN_MODEL", "gemma3:12b-it-qat")
OLLAMA_HOST = os.environ.get("TRACE_OLLAMA_HOST", "http://127.0.0.1:11434")
CAPTURES = ROOT / "data" / "phone_captures"
SECRETS = ROOT / ".secrets" / "frontier.env"

# P0 honesty: secure-by-default. Bind to loopback unless explicitly opened;
# require a shared token when one is set; no wildcard CORS; frontier OFF unless
# the operator explicitly enables it (so "stays on device" is the default truth).
BIND = os.environ.get("TRACE_BIND", "127.0.0.1")
ALLOW_ORIGIN = os.environ.get("TRACE_ALLOW_ORIGIN", f"http://127.0.0.1:{PORT}")
TRACE_TOKEN = os.environ.get("TRACE_TOKEN", "")
FRONTIER_ENABLED = os.environ.get("TRACE_FRONTIER_ENABLED", "0") == "1"
TRACE_EVENTLOG = os.environ.get("TRACE_EVENTLOG", "0") == "1"

# Persistent cross-session memory (never delete, decay = retrieval cost)
_MEMORY_DB: sqlite3.Connection | None = None
_MEMORY_DB_LOCK = threading.Lock()

# TEST-ONLY observability. When enabled, raw JPEG frames are KEPT on disk after
# perception (normally they are deleted immediately). OFF by default.
DEBUG_FRAMES = os.environ.get("TRACE_DEBUG_FRAMES", "0") == "1"

# Transient frame queue for the Mac-side perceiver. Frames are held only long
# enough for the VLM to extract derived text, then deleted (privacy moat).
_FRAME_QUEUE: Path = CAPTURES / "_frame_queue"

_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _log(kind: str, **fields: Any) -> None:
    """One concise, tailable line per request so the loop is observable live."""
    parts = " ".join(
        f"{k}={v}" for k, v in fields.items() if v is not None and v != ""
    )
    print(f"[{time.strftime('%H:%M:%S')}] {kind:9s} {parts}", flush=True)

# Rolling in-memory store for the phone's LIVE perception stream. The native app
# POSTs every committed OBJECT/EVENT record to /capture/perception as it sees it;
# we accumulate them (newest-bounded) into moment "live" so /ask answers from what
# the phone is perceiving right now, with real elapsed-second citations.
_LIVE: dict[str, dict[str, Any]] = {}
_LIVE_LOCK = threading.Lock()
LIVE_MAX = int(os.environ.get("TRACE_LIVE_MAX", "600"))

# Mac-side perception: the phone streams frames; the Mac's local multimodal gemma3
# is the real perceiver (the tiny on-device FastVLM just parrots its prompt). A
# background worker perceives the LATEST streamed frame per moment (dropping backlog),
# and /ask consolidates the per-frame descriptions into one scene and answers.
PERCEIVE = os.environ.get("TRACE_PERCEIVE", "1") == "1"
INSTANCE_PIPE = os.environ.get("TRACE_INSTANCE_PIPE", "0") == "1"
_VISION: dict[str, dict[str, Any]] = {}          # moment -> {t0, frames:[{t,frame,desc}]}
_VISION_LOCK = threading.Lock()
_PENDING: dict[str, list[Path]] = {}              # moment -> FIFO queue of frames awaiting perception
_PENDING_LOCK = threading.Lock()
# GPU contention guard: the perception worker (gemma3-vision + GroundingDINO + crop
# VLM) and the Q&A cascade (gemma3:12b) both hit the GPU; running together OOMs the
# M2's 32GB ("kIOGPUCommandBufferCallbackErrorOutOfMemory"). While a question is being
# answered, the perception worker pauses so only one GPU-heavy job runs at a time.
_ASK_ACTIVE = threading.Event()
_SCENE_CACHE: dict[str, dict[str, Any]] = {}      # moment -> {n, scene} (rebuild only on new frames)
_INSTANCE_GRAPHS: dict[str, dict[str, Any]] = {}  # moment -> scene graph from instance pipeline


def _frame_is_usable(path: Path) -> bool:
    """Quick quality gate: reject frames that are too small (dark/corrupt) or
    likely blurry (low file-size proxy — a sharp JPEG of a real scene is >8kB).
    No heavy CV deps; just file-size heuristic + basic JPEG header check."""
    try:
        sz = path.stat().st_size
    except OSError:
        return False
    if sz < 3000:
        return False
    header = path.read_bytes()[:3]
    if header[:2] != b"\xff\xd8":
        return False
    # Real sharpness/brightness gate (Laplacian variance) when available — keep
    # only sharp frames so the VLM never perceives motion-blur. Graceful fallback.
    try:
        import frame_quality
        if not frame_quality.quality(str(path)).get("keep", True):
            _log("FRAME-BLUR", frame=path.name)
            return False
    except Exception:
        pass
    return True


def _inject_perceived_record(moment: str, desc: str, frame_name: str,
                             pose: dict[str, Any] | None) -> None:
    """Write the Mac-VLM's perceived text back into kf_memory so the
    flat-string brain path can also use it. This is the key bridge."""
    with _LIVE_LOCK:
        store = _LIVE.setdefault(moment, {"t0": time.time(), "records": []})
        idx = len(store["records"])
        record: dict[str, Any] = {
            "t": round(time.time() - store["t0"], 1),
            "frame": f"f_{idx}",
            "caption": desc,
            "ocr": _extract_ocr_lines(desc),
            "source": "mac_vision",
            "scene": "perceived",
        }
        if pose:
            record["pose"] = pose
        store["records"].append(scrub_record(record))
        if len(store["records"]) > LIVE_MAX:
            store["records"] = store["records"][-LIVE_MAX:]
        recs = list(store["records"])
    mdir = _moment_dir(moment)
    (mdir / "kf_memory.json").write_text(json.dumps(recs, ensure_ascii=False))


_PLAUS_CACHE: dict[tuple, float] = {}


def _plausibility(candidate: str, activity: str) -> float:
    """Local-LLM prior for the compounding brain: how plausible is `candidate` in an
    `activity` scene (0..1)? Resolves conflicting reads (kitchen: soya yes, rocks no).
    Cached per (candidate, activity)."""
    key = (str(candidate).lower().strip(), activity)
    if key in _PLAUS_CACHE:
        return _PLAUS_CACHE[key]
    prompt = (f"In a typical {activity} scene, how plausible is it to see '{candidate}'? "
              f"Reply with ONLY a number from 0 to 1 (0 = impossible, 1 = very likely).")
    score = 0.5
    try:
        import ask_home
        out = ask_home._ollama(prompt, MODEL, OLLAMA_HOST, 15)
        m = re.search(r"\b([01](?:\.\d+)?|0?\.\d+)\b", str(out))
        if m:
            score = max(0.0, min(1.0, float(m.group(1))))
    except Exception:
        score = 0.5
    _PLAUS_CACHE[key] = score
    return score


def _moment_perception(moment: str, mdir: Path) -> dict[str, Any]:
    """Assemble a moment's derived perception (objects/texts/caption) for the
    activity identifier + domain specialists."""
    objects: list[str] = []
    texts: list[str] = []
    captions: list[str] = []
    g = _INSTANCE_GRAPHS.get(moment) or {}
    cons = g.get("consolidated") or {}
    for n in (cons.get("instances") or []):
        if n.get("type"):
            objects.append(str(n["type"]))
        for t in (n.get("texts") or []):
            texts.append(str(t))
    try:
        kf = json.load(open(mdir / "kf_memory.json"))
        for r in kf[-40:]:
            if r.get("caption"):
                captions.append(str(r["caption"]))
            for o in (r.get("ocr") or []):
                texts.append(str(o))
    except Exception:
        pass
    return {"objects": objects, "texts": texts, "caption": " ".join(captions)[:4000]}


def _persist_instance_graph(moment: str) -> None:
    """Persist the accumulated world/instance graph (coordinate nodes, relations,
    frame accumulation) so counting/spatial memory survives a brain restart — not
    just the flat kf_memory + eventlog. Founder mandate: never lose memory."""
    graph = _INSTANCE_GRAPHS.get(moment)
    if not graph:
        return
    try:
        mdir = _moment_dir(moment)
        tmp = mdir / "instance_graph.json.tmp"
        tmp.write_text(json.dumps(graph, ensure_ascii=False, default=float))
        tmp.replace(mdir / "instance_graph.json")
    except Exception as exc:
        _log("IGRAPH-SAVE-ERR", moment=moment, err=str(exc)[:80])


def _load_instance_graphs() -> None:
    """Reload persisted instance graphs on startup so accumulated coordinate memory
    continues across restarts instead of resetting."""
    if not INSTANCE_PIPE or not CAPTURES.exists():
        return
    for mdir in CAPTURES.iterdir():
        f = mdir / "instance_graph.json"
        if not f.is_file():
            continue
        try:
            graph = json.loads(f.read_text())
            _INSTANCE_GRAPHS[mdir.name] = graph
            cons = (graph.get("consolidated") or {})
            _log("IGRAPH-LOAD", moment=mdir.name,
                 nodes=len(cons.get("instances", [])),
                 frames=len(graph.get("_frame_instances", [])))
        except Exception as exc:
            _log("IGRAPH-LOAD-ERR", moment=mdir.name, err=str(exc)[:80])


def _perception_worker() -> None:
    import mac_vision_perceive as mv  # local gemma3-vision

    while True:
        # Pop the oldest pending frame across all moments (FIFO drain — every
        # streamed frame is perceived, none dropped for coverage).
        next_item: tuple[str, Path] | None = None
        with _PENDING_LOCK:
            for moment, paths in _PENDING.items():
                if paths:
                    next_item = (moment, paths.pop(0))
                    break
        if next_item is None:
            time.sleep(0.5)
            continue
        # Yield the GPU while a question is being answered (avoid OOM).
        while _ASK_ACTIVE.is_set():
            time.sleep(0.3)
        moment, path = next_item
        if True:
            if not path.exists():
                continue
            if not _frame_is_usable(path):
                _log("FRAME-SKIP", moment=moment, frame=path.name, reason="quality")
                if not DEBUG_FRAMES:
                    path.unlink(missing_ok=True)
                    path.with_suffix(".pose.json").unlink(missing_ok=True)
                continue
            pose_data: dict[str, Any] | None = None
            pose_file = path.with_suffix(".pose.json")
            if pose_file.exists():
                try:
                    pose_data = json.loads(pose_file.read_text())
                except Exception:
                    pass
            try:
                desc = mv.perceive_frame(path)
            except Exception as exc:
                _log("PERCEIVE-ERR", moment=moment, err=str(exc)[:80])
                if not DEBUG_FRAMES:
                    path.unlink(missing_ok=True)
                    pose_file.unlink(missing_ok=True)
                continue
            if INSTANCE_PIPE:
                try:
                    import instance_brain_wire as ibw
                    import math
                    # PoseStamper yaw/pitch are radians (CoreMotion/ARKit); the
                    # consolidator individuates by bearing in DEGREES.
                    _pose_deg: dict[str, float] | None = None
                    if isinstance(pose_data, dict):
                        def _deg(key: str) -> float | None:
                            v = pose_data.get(key)
                            try:
                                return float(v) * 180.0 / math.pi if v is not None else None
                            except Exception:
                                return None
                        _y, _p = _deg("yaw"), _deg("pitch")
                        if _y is not None or _p is not None:
                            _pose_deg = {"yaw": _y or 0.0, "pitch": _p or 0.0}
                    # Depth grid (ARKit raycast -> world points) for coordinate binding.
                    _depth_grid = None
                    _depth_file = path.with_suffix(".depth.json")
                    if _depth_file.exists():
                        try:
                            _depth_grid = json.loads(_depth_file.read_text())
                        except Exception:
                            _depth_grid = None
                    graph = ibw.perceive_and_graph(str(path), moment, _INSTANCE_GRAPHS,
                                                   pose=_pose_deg, depth_grid=_depth_grid)
                    text_rec = ibw.graph_to_text_record(graph)
                    if text_rec:
                        _inject_perceived_record(moment, text_rec, path.name + ".graph", pose_data)
                    _log("INST-GRAPH", moment=moment, nodes=len(graph.get("nodes", [])),
                         edges=len(graph.get("edges", [])))
                    _persist_instance_graph(moment)
                except Exception as exc:
                    _log("INST-PIPE-ERR", moment=moment, err=str(exc)[:80])
            # Privacy: delete the raw frame now that we have derived text.
            if not DEBUG_FRAMES:
                path.unlink(missing_ok=True)
                pose_file.unlink(missing_ok=True)
                path.with_suffix(".depth.json").unlink(missing_ok=True)
            with _VISION_LOCK:
                store = _VISION.setdefault(moment, {"t0": time.time(), "frames": []})
                store["frames"].append(
                    {"t": round(time.time() - store["t0"], 1), "frame": path.name, "desc": desc}
                )
                if len(store["frames"]) > 240:
                    store["frames"] = store["frames"][-240:]
                n = len(store["frames"])
            _inject_perceived_record(moment, desc, path.name, pose_data)
            _log("PERCEIVE", moment=moment, frame=path.name, n=n,
                 desc=desc.replace("\n", " ")[:70])


def _extract_ocr_lines(text: str) -> list[str]:
    """Recover verbatim OCR lines embedded in live derived-text packets."""
    lines: list[str] = []
    for quoted in re.findall(
        r"(?:provisional OCR text|OCR text|full-res OCR):\s*\"([^\"]+)\"",
        text,
        flags=re.IGNORECASE,
    ):
        lines.extend(part.strip() for part in quoted.splitlines() if part.strip())
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.upper().startswith("TEXT:"):
            continue
        value = line.split(":", 1)[1].strip()
        if not value or value.upper() == "NONE":
            continue
        lines.extend(part.strip() for part in re.split(r"\s*\|\s*", value) if part.strip())
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = re.sub(r"\s+", " ", line).strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_anchor(records: list[dict[str, Any]]) -> float | None:
    anchors: list[float] = []
    for record in records:
        t = _float_or_none(record.get("t"))
        if t is not None:
            anchors.append(t)
    return max(anchors) if anchors else None


def _load_kf_records(mem_path: Path) -> list[dict[str, Any]]:
    try:
        loaded = json.load(open(mem_path))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    return loaded if isinstance(loaded, list) else []


def _anchor_from_payload(payload: dict[str, Any], records: list[dict[str, Any]]) -> float | None:
    anchor = _float_or_none(payload.get("anchor"))
    return anchor if anchor is not None else _latest_anchor(records)


def _answer_payload(
    result: dict[str, Any],
    answer: str,
    anchor: float | None,
    elapsed_s: float,
) -> dict[str, Any]:
    scenes = result.get("scenes", [])
    source = result.get("source") or "local"
    refused = bool(result.get("refused")) or ask_home._is_refusal(answer)
    if not scenes and source != "ocr_consensus":
        refused = True
    citations = _citations_from_scenes(scenes)
    if not citations and source == "ocr_consensus" and anchor is not None and not refused:
        citations = [{"t": anchor, "frame": None, "label": f"{anchor:.1f}s"}]
    return {
        "answer": answer,
        "citations": citations,
        "source": source,
        "refused": bool(refused),
        "model": MODEL,
        "latency_s": round(elapsed_s, 1),
    }


def _with_eventlog_fields(out: dict[str, Any]) -> dict[str, Any]:
    if TRACE_EVENTLOG:
        out.setdefault("personal_evidence", "")
        out.setdefault("world_context", "")
    return out


def _capture(payload: dict[str, Any]) -> dict[str, Any]:
    mtext = str(payload.get("memory_text") or "").strip()
    # Drop the "nothing reliably visible" scene filler — it's noise for Q&A.
    if not mtext or "no reliable object" in mtext.lower():
        return {"ok": True, "skipped": True}
    moment = str(payload.get("moment_id") or "live")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    location_hint = str(payload.get("location_hint") or "").strip()
    with _LIVE_LOCK:
        store = _LIVE.setdefault(moment, {"t0": time.time(), "records": []})
        if not store["records"]:
            _path = _moment_dir(moment) / "kf_memory.json"
            if _path.exists():
                try:
                    _existing = json.load(open(_path))
                    if isinstance(_existing, list):
                        store["records"] = _existing[-LIVE_MAX:]
                except Exception:
                    pass
        idx = len(store["records"])
        # Scrub PII before it ever enters the in-RAM store or the persisted file:
        # what we retain is only the redacted words it read (the privacy moat, enforced).
        rec: dict[str, Any] = {
            "t": round(time.time() - store["t0"], 1),
            "frame": f"f_{idx}",
            "caption": mtext,
            "ocr": _extract_ocr_lines(mtext),
            "source": str(payload.get("source") or "native"),
            "scene": payload.get("scene_phase"),
            "location_hint": location_hint or None,
            "metadata": dict(metadata),
        }
        pose = metadata.get("pose")
        if isinstance(pose, dict) and pose:
            rec["pose"] = pose
        store["records"].append(scrub_record(rec))
        if len(store["records"]) > LIVE_MAX:
            store["records"] = store["records"][-LIVE_MAX:]
        recs = list(store["records"])
    mdir = _moment_dir(moment)
    (mdir / "kf_memory.json").write_text(json.dumps(recs, ensure_ascii=False))
    last = recs[-1]
    if TRACE_EVENTLOG:
        last_metadata = last.get("metadata")
        if not isinstance(last_metadata, dict):
            last_metadata = {}
        pose = last_metadata.get("pose")
        if not isinstance(pose, dict):
            pose = None
        append_perception_observations(
            mdir / "events.db",
            moment_id=moment,
            t_seconds=float(last.get("t") or 0.0),
            memory_text=str(last.get("caption") or ""),
            ocr_lines=tuple(last.get("ocr") or ()),
            pose=pose,
            location_hint=str(last.get("location_hint") or "").strip() or None,
        )
    _log(
        "CAPTURE",
        moment=moment,
        n=len(recs),
        t=last.get("t"),
        ocr=len(last.get("ocr") or []) or None,
        txt=(last.get("caption") or "").splitlines()[0][:90],
    )
    return {"ok": True, "moment_id": moment, "frames": len(recs), "t": recs[-1]["t"]}


def _receive_video(stream, length: int, path: str) -> dict[str, Any]:
    """Receive the FULL captured video (raw .mov bytes) and save it on the Mac so
    the moment is recorded continuously, not as sparse keyframes. Streamed to disk
    in chunks (the file can be large)."""
    from urllib.parse import parse_qs, urlparse
    qs = parse_qs(urlparse(path).query)
    frames = (qs.get("frames") or ["?"])[0]
    vdir = CAPTURES / "live" / "video"
    vdir.mkdir(parents=True, exist_ok=True)
    name = f"capture_{int(_now())}.mov"
    dest = vdir / name
    written = 0
    with open(dest, "wb") as f:
        remaining = length
        while remaining > 0:
            chunk = stream.read(min(1 << 20, remaining))
            if not chunk:
                break
            f.write(chunk)
            written += len(chunk)
            remaining -= len(chunk)
    _log("VIDEO", file=name, mb=round(written / 1e6, 1), frames=frames)
    return {"ok": True, "file": name, "bytes": written, "frames": frames}


def _now() -> float:
    import time as _t
    return _t.time()


def _receive_frame(payload: dict[str, Any]) -> dict[str, Any]:
    """Receive a raw frame from the phone for Mac-side VLM perception.
    The frame is written to a transient queue; the perception worker picks it
    up, extracts derived text, and deletes the frame. No raw media persists
    unless DEBUG_FRAMES is on (test-only). This is the PRODUCT path — the Mac
    VLM is the real perceiver; the phone's tiny FastVLM is just a trigger."""
    import base64

    moment = str(payload.get("moment_id") or "live")
    b64 = str(payload.get("jpeg_b64") or "")
    if not b64:
        return {"ok": False, "error": "no jpeg_b64"}
    try:
        data = base64.b64decode(b64)
    except Exception as exc:
        return {"ok": False, "error": f"bad base64: {exc}"}
    # Write to transient queue (perceived then deleted) or debug dir (kept).
    if DEBUG_FRAMES:
        fdir = _moment_dir(moment) / "debug_frames"
    else:
        fdir = _FRAME_QUEUE / moment
    fdir.mkdir(parents=True, exist_ok=True)
    t = _float_or_none(payload.get("t"))
    name = f"{t:08.1f}.jpg" if t is not None else f"{len(list(fdir.glob('*.jpg'))):05d}.jpg"
    (fdir / name).write_bytes(data)
    # Save pose + depth grid alongside the frame so the perceiver can project each
    # detected instance to a world coordinate (the world-anchored binder substrate).
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("pose"):
        (fdir / name).with_suffix(".pose.json").write_text(
            json.dumps(metadata["pose"], ensure_ascii=False)
        )
    if isinstance(metadata, dict) and metadata.get("depth_grid"):
        (fdir / name).with_suffix(".depth.json").write_text(
            json.dumps(metadata["depth_grid"], ensure_ascii=False)
        )
    if PERCEIVE:
        with _PENDING_LOCK:
            # FIFO queue per moment: perceive EVERY frame (after-the-moment Q&A
            # has no real-time constraint, so we never drop frames for coverage).
            # A generous cap guards against runaway backlog.
            q = _PENDING.setdefault(moment, [])
            q.append(fdir / name)
            if len(q) > 5000:
                drop = q.pop(0)
                drop.unlink(missing_ok=True)
                drop.with_suffix(".pose.json").unlink(missing_ok=True)
    _log("FRAME", moment=moment, file=name, bytes=len(data))
    return {"ok": True, "moment_id": moment, "file": name, "bytes": len(data)}


def _load_secret(name: str) -> str:
    """Read a key from .secrets/frontier.env (gitignored) or the environment."""
    if os.environ.get(name):
        return os.environ[name]
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                v = v.strip().strip('"').strip("'")
                return re.sub(r"\s+", "", v)  # API keys never contain whitespace
    return ""


def _frontier_available() -> str:
    if _load_secret("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _load_secret("OPENAI_API_KEY"):
        return "openai"
    return ""


def _get_memory_db() -> sqlite3.Connection:
    global _MEMORY_DB
    with _MEMORY_DB_LOCK:
        if _MEMORY_DB is None:
            _MEMORY_DB = brain_memory.open_db(CAPTURES)
            n = brain_memory.session_count(_MEMORY_DB)
            _log("MEMORY", msg=f"opened durable store ({n} prior sessions)")
        return _MEMORY_DB


def _moment_dir(moment_id: str) -> Path:
    safe = _SAFE.sub("", moment_id or "")[:64] or "moment"
    out = CAPTURES / safe
    out.mkdir(parents=True, exist_ok=True)
    return out


def _records_to_kf(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the phone's derived-text records into ask_home keyframe records.

    Each phone record is one OBJECT/EVENT/OCR observation with a timestamp. We
    map its text into ``caption`` (so retrieval/description see it) and any
    verbatim reads into ``ocr`` (so reading questions can cite exact text).
    """
    kf: list[dict[str, Any]] = []
    for idx, rec in enumerate(records or []):
        text = str(rec.get("text") or "").strip()
        ocr = rec.get("ocr") or []
        if isinstance(ocr, str):
            ocr = [ocr]
        ocr = [str(x).strip() for x in ocr if str(x).strip()]
        if not ocr:
            ocr = _extract_ocr_lines(text)
        if not text and not ocr:
            continue
        # Scrub PII at the storage seam — the persisted memory holds only redacted reads.
        kf.append(
            scrub_record(
                {
                    "t": float(rec.get("t", idx)),
                    "frame": f"f_{idx}",
                    "caption": text,
                    "ocr": ocr,
                    "source": str(rec.get("source") or "native"),
                }
            )
        )
    return kf


def _write_memory(moment_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    mdir = _moment_dir(moment_id)
    kf = _records_to_kf(records)
    (mdir / "kf_memory.json").write_text(json.dumps(kf, indent=2, ensure_ascii=False))
    speech = [
        r
        for r in kf
        if "nearby speech" in r["caption"].lower() or "transcript" in r["caption"].lower()
    ]
    # Persist to durable cross-session memory
    try:
        db = _get_memory_db()
        result = brain_memory.ingest_session(db, moment_id, kf)
        _log("MEMORY", moment=moment_id,
             facts=result["facts_stored"], entities=result["entities_found"])
    except Exception as exc:
        _log("MEMORY-ERR", moment=moment_id, err=str(exc)[:80])
    return {
        "ok": True,
        "moment_id": moment_id,
        "frames": len(kf),
        "speech_records": len(speech),
        "store": str(mdir / "kf_memory.json"),
    }


def _citations_from_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[float] = set()
    cites: list[dict[str, Any]] = []
    for s in scenes or []:
        t = s.get("t")
        if t is None or t in seen:
            continue
        seen.add(t)
        cites.append({"t": t, "frame": s.get("frame"), "label": f"{float(t):.1f}s"})
    return cites[:8]


def _frontier_answer(question: str, kf: list[dict[str, Any]]) -> dict[str, Any]:
    """Answer from the DERIVED TEXT only, via a frontier text model (opt-in).

    Only the text the phone already derived is sent — never an image, never audio.
    The model is held to the same discipline as the local brain: answer strictly
    from the provided observations with timestamps, or honestly say it isn't there.
    """
    provider = _frontier_available()
    if not provider:
        return {"answer": "", "source": "", "error": "no frontier key"}

    lines = []
    for r in kf:
        txt = r["caption"]
        if r.get("ocr"):
            txt += "  TEXT: " + "; ".join(r["ocr"])
        lines.append(f"[{float(r['t']):.1f}s] {txt}")
    context = "\n".join(lines)[:24000]
    sys_prompt = (
        "You are TRACE's memory brain. You are given a time-stamped log of "
        "observations that were derived on-device from a first-person camera "
        "(no raw image or audio is available to you — only this text). Answer the "
        "question STRICTLY from these observations. Cite the timestamps you used "
        "like (12.3s). If the observations do not contain the answer, reply "
        "exactly: I don't have that in my memory. Never guess."
    )
    user = f"OBSERVATIONS:\n{context}\n\nQUESTION: {question}"

    if provider == "anthropic":
        key = _load_secret("ANTHROPIC_API_KEY")
        model = os.environ.get("TRACE_FRONTIER_MODEL", "claude-sonnet-4-6")
        body = json.dumps(
            {
                "model": model,
                "max_tokens": 600,
                "system": sys_prompt,
                "messages": [{"role": "user", "content": user}],
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        text = "".join(b.get("text", "") for b in data.get("content", []))
        return {"answer": text.strip(), "source": f"frontier:{model}"}

    # openai
    key = _load_secret("OPENAI_API_KEY")
    model = os.environ.get("TRACE_FRONTIER_MODEL", "gpt-4o")
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 600,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ],
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    text = data["choices"][0]["message"]["content"]
    return {"answer": text.strip(), "source": f"frontier:{model}"}


def _eventlog_world_knowledge_oracle(prompt: str) -> str:
    return ask_home._ollama(prompt, MODEL, OLLAMA_HOST, 15)


def _kf_fulltext_answer(
    question: str, kf: list[dict[str, Any]], t0: float,
    rich_only: bool = False,
) -> dict[str, Any] | None:
    """Search kf_memory captions/descriptions for relevant snippets, then ask
    the LLM to answer. When rich_only=True (eventlog already grounded-refused),
    only consider mac_vision and instance pipeline entries — these are richer
    than what eventlog had and may contain the answer."""
    if not kf:
        return None
    rich_sources = {"mac_vision", "instance_pipeline"}
    q_lower = question.lower()
    q_words = set(re.split(r'\W+', q_lower)) - {
        "", "the", "a", "an", "is", "are", "was", "were", "did", "do", "does",
        "what", "how", "many", "which", "who", "where", "when", "why",
        "my", "i", "me", "you", "your", "we", "our", "they", "their", "its",
        "there", "any", "on", "in", "of", "it", "to", "for", "at", "by",
        "with", "from", "about", "that", "this", "have", "has", "had",
        "be", "been", "can", "could", "would", "should", "not", "no",
        "or", "and", "but", "if", "so", "see", "saw", "s",
    }
    scored: list[tuple[float, dict[str, Any]]] = []
    for rec in kf:
        cap = str(rec.get("caption", ""))
        cap_lower = cap.lower()
        src = rec.get("source", "")
        if not cap or len(cap) < 20:
            continue
        is_rich = src in rich_sources or "INSTANCES" in cap[:30]
        if rich_only and not is_rich:
            continue
        hits = sum(1 for w in q_words if w in cap_lower)
        if hits == 0:
            continue
        boost = 2.0 if is_rich else 1.0
        scored.append((hits * boost / max(len(q_words), 1), rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:8]
    if not top:
        return None
    snippets = []
    for score, rec in top:
        t = rec.get("t", "?")
        src = rec.get("source", "?")
        max_len = 1200 if src in rich_sources else 600
        cap = str(rec.get("caption", ""))[:max_len]
        snippets.append(f"[{t}s, {src}] {cap}")
    context = "\n---\n".join(snippets)
    prompt = (
        "You answer questions about what a person saw, using ONLY the captured data below.\n"
        "Rules:\n"
        "(1) Only state things directly supported by the data.\n"
        "(2) If the data contains the answer, give it concisely.\n"
        "(3) On-screen content (chat apps, websites, videos) is valid — report what was on screen.\n"
        "(4) Read carefully: distinguish WHO sent a message from WHAT the message says. "
        "In chat data 'Deepak: Happy birthday navin' means Deepak SENT it and navin is the SUBJECT.\n"
        "(5) If the data genuinely does not contain the answer, say: "
        "\"I don't have that in what I saw.\"\n\n"
        f"CAPTURED DATA:\n{context}\n\n"
        f"QUESTION: {question}\nANSWER:"
    )
    try:
        ans = ask_home._ollama(prompt, MODEL, OLLAMA_HOST, 120)
    except Exception:
        return None
    refused = ask_home._is_refusal(ans)
    cites = [{"t": rec.get("t", 0), "label": f"{rec.get('t', 0)}s"}
             for _, rec in top[:3]]
    return {
        "answer": ans,
        "citations": cites,
        "source": "kf_search",
        "refused": bool(refused),
        "model": MODEL,
        "latency_s": round(time.time() - t0, 1),
    }


def _ask(payload: dict[str, Any]) -> dict[str, Any]:
    """Pause the perception worker for the duration of the answer (GPU guard),
    then run the answer cascade."""
    _ASK_ACTIVE.set()
    try:
        return _ask_impl(payload)
    finally:
        _ASK_ACTIVE.clear()


def _ask_impl(payload: dict[str, Any]) -> dict[str, Any]:
    moment = str(payload.get("moment_id") or "")
    question = str(payload.get("question") or "").strip()
    allow_frontier = bool(payload.get("allow_frontier", False)) and FRONTIER_ENABLED

    # INJECT path runs AFTER eventlog (below) — see the inject block after the
    # eventlog check. Eventlog is the typed system and takes priority.

    if payload.get("records"):  # ingest-then-ask in one shot
        _write_memory(moment, payload["records"])
    mdir = _moment_dir(moment)
    mem_path = mdir / "kf_memory.json"
    if not mem_path.exists():
        return _with_eventlog_fields({
            "answer": "Capture a moment first, then ask me about it.",
            "citations": [],
            "source": "none",
            "refused": True,
        })
    if not question:
        return _with_eventlog_fields({
            "answer": "Ask me something about what you captured.",
            "citations": [],
            "source": "none",
            "refused": True,
        })

    kf_for_anchor = _load_kf_records(mem_path)
    anchor = _anchor_from_payload(payload, kf_for_anchor)

    t0 = time.time()
    best_refused: dict[str, Any] | None = None
    eventlog_grounded_refusal = False

    # --- Source 1: eventlog (typed observations) ---
    if TRACE_EVENTLOG:
        eventlog_path = mdir / "events.db"
        if eventlog_path.exists():
            eventlog_result = eventlog_answer(
                question,
                eventlog_path,
                world_knowledge_oracle=_eventlog_world_knowledge_oracle,
            )
            if eventlog_result.supported:
                scenes = [
                    {
                        "t": observation.t_ms / 1000.0,
                        "frame": observation.provenance.event_id,
                    }
                    for observation in eventlog_result.citations
                ]
                answer = eventlog_result.answer
                out = _answer_payload(
                    {"scenes": scenes, "source": "eventlog", "refused": eventlog_result.refused},
                    answer,
                    anchor,
                    time.time() - t0,
                )
                out["personal_evidence"] = eventlog_result.personal_evidence
                out["world_context"] = eventlog_result.world_context
                if not out["refused"]:
                    _log("ASK", moment=moment, q=question[:60], src="eventlog",
                         refused=False, ans=answer.replace("\n", " ")[:90])
                    return _with_eventlog_fields(out)
                best_refused = out
                eventlog_grounded_refusal = True

    # --- Source 2: instance graph (derived counts/relations) ---
    if INSTANCE_PIPE and moment in _INSTANCE_GRAPHS:
        try:
            import instance_brain_wire as ibw
            ig_result = ibw.answer_from_graph(question, moment, _INSTANCE_GRAPHS)
            if ig_result and not ig_result.get("refused"):
                ig_result["latency_s"] = round(time.time() - t0, 1)
                ig_result["model"] = MODEL
                ig_result["citations"] = []
                _log("ASK", moment=moment, q=question[:60], src="instance_graph",
                     refused=False, ans=ig_result["answer"].replace("\n", " ")[:90])
                return _with_eventlog_fields(ig_result)
        except Exception as exc:
            _log("INST-ASK-ERR", moment=moment, err=str(exc)[:80])

    # --- Source 2.5: activity specialists (domain understanding) ---
    # Recognise the activity (cooking/chess/...) and answer from the domain
    # specialist's structured facts — "how much soya", "what opening".
    try:
        import activity_dispatch
        _nodes = ((_INSTANCE_GRAPHS.get(moment) or {}).get("consolidated") or {}).get("instances") or []
        analysis = activity_dispatch.analyze(
            _moment_perception(moment, mdir), nodes=_nodes, plausibility_fn=_plausibility)
        if analysis and analysis.get("domain_facts"):
            dom = activity_dispatch.answer_domain(question, analysis["domain_facts"])
            if dom and not dom.get("refused"):
                dom["latency_s"] = round(time.time() - t0, 1)
                dom["model"] = MODEL
                dom["citations"] = []
                dom.setdefault("source", "specialist")
                _log("ASK", moment=moment, q=question[:60], src=dom["source"],
                     refused=False, ans=str(dom["answer"]).replace("\n", " ")[:90])
                return _with_eventlog_fields(dom)
    except Exception as exc:
        _log("DOMAIN-ERR", moment=moment, err=str(exc)[:80])

    # --- Source 3: kf_memory rich search (mac_vision + instance data) ---
    # Only runs when eventlog grounded-refused — these sources have data the
    # eventlog missed (physical object descriptions, brand labels).
    kf = _load_kf_records(mem_path)
    if eventlog_grounded_refusal:
        kf_answer = _kf_fulltext_answer(question, kf, t0, rich_only=True)
        if kf_answer and not kf_answer.get("refused"):
            _log("ASK", moment=moment, q=question[:60], src="kf_search",
                 refused=False, ans=kf_answer["answer"].replace("\n", " ")[:90])
            return _with_eventlog_fields(kf_answer)

    # --- Source 4: inject_structure (consensus-bound scene) ---
    if kf and len(kf) >= 3:
        import inject_structure
        t0_inj = time.time()
        scene = inject_structure.build_scene(kf)
        has_objects = any(o["confidence"] in ("medium", "high", "low") for o in scene["objects"])
        if has_objects:
            ans = inject_structure.answer_from_scene(scene, question, OLLAMA_HOST, MODEL)
            refused = ask_home._is_refusal(ans)
            cites = [{"t": r["t"], "label": f"{r['t']}s"} for r in kf[-3:] if "t" in r]
            out = {"answer": ans, "citations": cites, "source": "inject",
                   "refused": bool(refused), "model": MODEL,
                   "latency_s": round(time.time() - t0_inj, 1)}
            if not refused:
                _log("ASK", moment=moment, q=question[:60], src="inject",
                     refused=False, ans=ans.replace("\n", " ")[:90])
                return _with_eventlog_fields(out)
            if not best_refused:
                best_refused = out

    # --- Source 5: kf_memory broad search (all sources, only when eventlog
    # didn't grounded-refuse — avoids answering from ungrounded text) ---
    if not eventlog_grounded_refusal:
        kf_broad = _kf_fulltext_answer(question, kf, t0, rich_only=False)
        if kf_broad and not kf_broad.get("refused"):
            _log("ASK", moment=moment, q=question[:60], src="kf_search",
                 refused=False, ans=kf_broad["answer"].replace("\n", " ")[:90])
            return _with_eventlog_fields(kf_broad)

    # --- Source 6: long-term memory (cross-session recall) ---
    try:
        db = _get_memory_db()
        ltm_facts = brain_memory.recall(db, question, limit=8,
                                        current_session=moment)
        if ltm_facts:
            ltm_snippets = []
            for f in ltm_facts:
                ltm_snippets.append(
                    f"[session={f['session_id']}, {f['source']}] {f['caption'][:600]}"
                )
            ltm_context = "\n---\n".join(ltm_snippets)
            ltm_prompt = (
                "You answer questions using the person's PAST captured memories below.\n"
                "Rules: (1) Only state things supported by the data. "
                "(2) Distinguish past sessions from the current one. "
                "(3) If the data doesn't contain the answer, say: "
                "\"I don't have that in my past memories.\"\n\n"
                f"PAST MEMORIES:\n{ltm_context}\n\n"
                f"QUESTION: {question}\nANSWER:"
            )
            try:
                ltm_ans = ask_home._ollama(ltm_prompt, MODEL, OLLAMA_HOST, 120)
            except Exception:
                ltm_ans = None
            if ltm_ans and not ask_home._is_refusal(ltm_ans):
                cites = [{"t": f["t"], "label": f"past:{f['session_id'][:8]}"}
                         for f in ltm_facts[:3]]
                _log("ASK", moment=moment, q=question[:60], src="long_term_memory",
                     refused=False, ans=ltm_ans.replace("\n", " ")[:90])
                return _with_eventlog_fields({
                    "answer": ltm_ans, "citations": cites,
                    "source": "long_term_memory", "refused": False,
                    "model": MODEL, "latency_s": round(time.time() - t0, 1),
                })
    except Exception as exc:
        _log("LTM-ERR", moment=moment, err=str(exc)[:80])

    # --- Source 7: ask_home (semantic search + LLM answer) ---
    # Skip if eventlog already grounded-refused (ask_home would answer from the
    # same raw text that eventlog correctly determined is ungrounded).
    if not eventlog_grounded_refusal:
        _ask = getattr(ask_home, "ask_with_understanding", ask_home.ask)
        try:
            res = _ask(question, str(mem_path), MODEL, anchor=anchor)
        except TypeError:
            res = ask_home.ask(question, str(mem_path), MODEL, anchor=anchor)
        answer = res.get("answer", "")
        out = _answer_payload(res, answer, anchor, time.time() - t0)

        if not out["refused"]:
            _log("ASK", moment=moment, q=question[:60], src=out.get("source"),
                 refused=False, ans=answer.replace("\n", " ")[:90])
            return _with_eventlog_fields(out)

        # --- Source 6: frontier (if local refused) ---
        if allow_frontier and _frontier_available():
            kf_mem = ask_home.load_memory(str(mem_path))
            try:
                fr = _frontier_answer(question, kf_mem)
                if fr.get("answer") and not ask_home._is_refusal(fr["answer"]):
                    out["answer"] = fr["answer"]
                    out["source"] = fr["source"]
                    out["refused"] = False
                    out["local_refused_first"] = True
                    _log("ASK", moment=moment, q=question[:60], src=out["source"],
                         refused=False, ans=out["answer"].replace("\n", " ")[:90])
                    return _with_eventlog_fields(out)
            except Exception as exc:
                out["frontier_error"] = str(exc)

    # All sources refused — return the best refusal (prefer eventlog for citations)
    final = best_refused or out
    _log(
        "ASK",
        moment=moment,
        q=question[:70],
        refused=True,
        src=final.get("source"),
        lat=round(time.time() - t0, 1),
        ans=(final.get("answer") or "").replace("\n", " ")[:100],
    )
    return _with_eventlog_fields(final)


def _proof(moment: str) -> dict[str, Any]:
    """Audit the moment's store: prove zero raw media, count text records."""
    mdir = _moment_dir(moment)
    raw_exts = {".jpg", ".jpeg", ".png", ".heic", ".mov", ".mp4", ".wav", ".m4a", ".aac"}
    raw = [str(p) for p in mdir.rglob("*") if p.suffix.lower() in raw_exts]
    kf_path = mdir / "kf_memory.json"
    n = 0
    if kf_path.exists():
        try:
            n = len(json.load(open(kf_path)))
        except Exception:
            n = 0
    return {
        "moment_id": moment,
        "raw_media_files": len(raw),
        "raw_media_list": raw[:5],
        "text_records": n,
        "store": str(mdir),
        "moat_intact": len(raw) == 0,
    }


_FIELD_KEYS = ("SCENE", "OBJECTS", "TEXT", "PEOPLE")


def _timeline(moment: str) -> dict[str, Any]:
    """The moment's derived-text records, parsed into display fields for the
    pitch surface. This is the only thing the store holds — there is no image to
    return, by design."""
    mdir = _moment_dir(moment)
    p = mdir / "kf_memory.json"
    recs: list[dict[str, Any]] = []
    if p.exists():
        try:
            recs = json.load(open(p))
        except Exception:
            recs = []
    out = []
    for r in recs:
        cap = str(r.get("caption") or "")
        fields = {"scene": "", "objects": "", "text": "", "people": ""}
        for line in cap.splitlines():
            for k in _FIELD_KEYS:
                if line.strip().upper().startswith(k + ":"):
                    fields[k.lower()] = line.split(":", 1)[1].strip()
        ocr = r.get("ocr") or []
        out.append(
            {
                "t": r.get("t"),
                "frame": r.get("frame"),
                "raw": cap,
                "ocr": ocr if isinstance(ocr, list) else [ocr],
                **fields,
            }
        )
    return {"moment_id": moment, "count": len(out), "model": MODEL, "records": out}


def _demo_html() -> bytes:
    path = ROOT / "scripts" / "pitch_demo.html"
    try:
        return path.read_bytes()
    except Exception:
        return b"<h1>pitch_demo.html not found</h1>"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a: Any) -> None:
        return

    def _authed(self) -> bool:
        # Auth disabled when no token configured (local dev); set TRACE_TOKEN to enforce.
        if not TRACE_TOKEN:
            return True
        return self.headers.get("X-TRACE-Token", "") == TRACE_TOKEN

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        if u.path in ("/proof", "/timeline") and not self._authed():
            self._json(401, {"error": "unauthorized"})
            return
        if u.path == "/health":
            self._json(200, {"ok": True, "model": MODEL, "frontier": _frontier_available() or None})
        elif u.path == "/proof":
            moment = (parse_qs(u.query).get("moment_id") or [""])[0]
            self._json(200, _proof(moment))
        elif u.path == "/timeline":
            moment = (parse_qs(u.query).get("moment_id") or [""])[0]
            self._json(200, _timeline(moment))
        elif u.path == "/memory":
            try:
                db = _get_memory_db()
                self._json(200, {
                    "sessions": brain_memory.session_count(db),
                    "entities": brain_memory.known_entities(db, 30),
                })
            except Exception as exc:
                self._json(500, {"error": str(exc)[:200]})
        elif u.path in ("/", "/demo", "/pitch"):
            self._send(200, _demo_html(), "text/html; charset=utf-8")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authed():
            self._json(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        # Full-video upload: the body is raw .mov bytes, not JSON — save it.
        if self.path.split("?")[0] == "/debug/video":
            self._json(200, _receive_video(self.rfile, length, self.path))
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        try:
            if self.path == "/capture/perception":
                self._json(200, _capture(payload))
            elif self.path == "/debug/frame":
                self._json(200, _receive_frame(payload))
            elif self.path == "/ingest":
                self._json(
                    200,
                    _write_memory(
                        str(payload.get("moment_id") or ""), payload.get("records") or []
                    ),
                )
            elif self.path == "/ask":
                self._json(200, _ask(payload))
            else:
                self._json(404, {"error": "no route"})
        except Exception as exc:
            print(f"  ERR {self.path}: {exc}", file=sys.stderr, flush=True)
            self._json(500, {"error": str(exc)})


def main() -> int:
    CAPTURES.mkdir(parents=True, exist_ok=True)
    _FRAME_QUEUE.mkdir(parents=True, exist_ok=True)
    _load_instance_graphs()  # restore accumulated coordinate memory across restarts
    if PERCEIVE:
        threading.Thread(target=_perception_worker, daemon=True).start()
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    fr = (
        _frontier_available() if FRONTIER_ENABLED else "off (set TRACE_FRONTIER_ENABLED=1)"
    ) or "off"
    auth = "token-required" if TRACE_TOKEN else "OPEN (set TRACE_TOKEN to lock)"
    print(
        f"TRACE brain live on http://{BIND}:{PORT}  model={MODEL}  frontier={fr}  auth={auth}",
        flush=True,
    )
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
