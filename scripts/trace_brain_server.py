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
from scrub_pii import scrub_record  # noqa: E402  on-device PII redaction at the storage seam

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

_SAFE = re.compile(r"[^a-zA-Z0-9_-]")

# Rolling in-memory store for the phone's LIVE perception stream. The native app
# POSTs every committed OBJECT/EVENT record to /capture/perception as it sees it;
# we accumulate them (newest-bounded) into moment "live" so /ask answers from what
# the phone is perceiving right now, with real elapsed-second citations.
_LIVE: dict[str, dict[str, Any]] = {}
_LIVE_LOCK = threading.Lock()
LIVE_MAX = int(os.environ.get("TRACE_LIVE_MAX", "600"))


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


def _capture(payload: dict[str, Any]) -> dict[str, Any]:
    mtext = str(payload.get("memory_text") or "").strip()
    # Drop the "nothing reliably visible" scene filler — it's noise for Q&A.
    if not mtext or "no reliable object" in mtext.lower():
        return {"ok": True, "skipped": True}
    moment = str(payload.get("moment_id") or "live")
    with _LIVE_LOCK:
        store = _LIVE.setdefault(moment, {"t0": time.time(), "records": []})
        idx = len(store["records"])
        # Scrub PII before it ever enters the in-RAM store or the persisted file:
        # what we retain is only the redacted words it read (the privacy moat, enforced).
        store["records"].append(
            scrub_record(
                {
                    "t": round(time.time() - store["t0"], 1),
                    "frame": f"f_{idx}",
                    "caption": mtext,
                    "ocr": _extract_ocr_lines(mtext),
                    "source": str(payload.get("source") or "native"),
                    "scene": payload.get("scene_phase"),
                }
            )
        )
        if len(store["records"]) > LIVE_MAX:
            store["records"] = store["records"][-LIVE_MAX:]
        recs = list(store["records"])
    mdir = _moment_dir(moment)
    (mdir / "kf_memory.json").write_text(json.dumps(recs, ensure_ascii=False))
    return {"ok": True, "moment_id": moment, "frames": len(recs), "t": recs[-1]["t"]}


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


def _ask(payload: dict[str, Any]) -> dict[str, Any]:
    moment = str(payload.get("moment_id") or "")
    question = str(payload.get("question") or "").strip()
    allow_frontier = bool(payload.get("allow_frontier", False)) and FRONTIER_ENABLED
    if payload.get("records"):  # ingest-then-ask in one shot
        _write_memory(moment, payload["records"])
    mdir = _moment_dir(moment)
    mem_path = mdir / "kf_memory.json"
    if not mem_path.exists():
        return {
            "answer": "Capture a moment first, then ask me about it.",
            "citations": [],
            "source": "none",
            "refused": True,
        }
    if not question:
        return {
            "answer": "Ask me something about what you captured.",
            "citations": [],
            "source": "none",
            "refused": True,
        }

    kf_for_anchor = _load_kf_records(mem_path)
    anchor = _anchor_from_payload(payload, kf_for_anchor)

    t0 = time.time()
    res = ask_home.ask(question, str(mem_path), MODEL, anchor=anchor)
    answer = res.get("answer", "")
    out = _answer_payload(res, answer, anchor, time.time() - t0)

    if out["refused"] and allow_frontier and _frontier_available():
        kf = ask_home.load_memory(str(mem_path))
        try:
            fr = _frontier_answer(question, kf)
            if fr.get("answer") and not ask_home._is_refusal(fr["answer"]):
                out["answer"] = fr["answer"]
                out["source"] = fr["source"]
                out["refused"] = False
                out["local_refused_first"] = True
        except Exception as exc:  # frontier failure must not break the answer
            out["frontier_error"] = str(exc)
    return out


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
        elif u.path in ("/", "/demo", "/pitch"):
            self._send(200, _demo_html(), "text/html; charset=utf-8")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._authed():
            self._json(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        try:
            if self.path == "/capture/perception":
                self._json(200, _capture(payload))
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
