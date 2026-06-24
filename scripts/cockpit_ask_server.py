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
import re
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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

LIVE_MEM = ROOT / "data" / "phone_captures" / "live" / "kf_memory.json"
OCR_MEMO = Path("/tmp/ocr_memory.json")
MODEL = "gemma3:12b-it-qat"
OLLAMA = "http://127.0.0.1:11434"
ASK_TIMEOUT = 60
PAGE = ROOT / "scripts" / "cockpit_layman.html"
FEEDBACK = ROOT / "ops" / "cockpit" / "feedback.jsonl"
ABLATION = ROOT / "evaluation" / "ras" / "posthoc_ablation_n16.json"
DEMO_ASK_CACHE = ROOT / "ops" / "cockpit" / "demo_cache.json"

# The active memory path is resolved per request. Parsed counts are cached by
# file signature so status polling stays cheap while live capture is idle.
_MEM_LOCK = threading.Lock()
_LIVE_CACHE = {}
_DEMO_CACHE = {}
_DEMO_ASK_CACHE_SNAPSHOT = (None, {})
_ASK_LOCK = threading.Lock()


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
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

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
        elif path == "/api/status":
            memory = active_memory()
            engine_on = bool(ollama_up() and memory.get("path"))
            self._json({"engine_on": engine_on,
                        "things_remembered": memory["things_remembered"],
                        "mode": memory["mode"],
                        "capture": memory["capture"],
                        "last_capture": memory["last_capture"]})
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
