#!/usr/bin/env python3
"""TRACE — the live phone web app server (HTTPS over the LAN).

Open on the iPhone (same WiFi):  https://<mac-lan-ip>:8799

The camera runs IN the page (getUserMedia, which iOS only allows over HTTPS).
The phone grabs JPEG frames from its own live preview and POSTs only those --
no video is ever encoded or uploaded. The Mac reads each frame to text with
Apple Vision OCR, DELETES it on the spot, binds the text into consensus memory,
and answers questions with timestamped citations on local models. The
no-raw-media moat holds live: nothing but derived text is ever stored.

Run with the venv python (needs ocrmac + trace + a local Ollama):
    TRACE_PORT=8799 .venv/bin/python scripts/trace_app.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from phone_perceive import perceive_frames  # noqa: E402

import ask_home  # noqa: E402  the brain (consensus OCR + WS1 self/world guard + binder)

PORT = int(os.environ.get("TRACE_PORT", "8799"))
MODEL = os.environ.get("TRACE_MODEL", "gemma3:12b-it-qat")
CAPTURES = ROOT / "data" / "phone_captures"
WEB = ROOT / "web" / "trace_app.html"
CERT = ROOT / "ops" / "certs" / "trace_cert.pem"
KEY = ROOT / "ops" / "certs" / "trace_key.pem"

_SAFE = re.compile(r"[^a-zA-Z0-9_-]")


def _moment_dir(moment_id: str) -> Path:
    """A per-moment memory dir, with the id sanitised to a safe path segment."""
    safe = _SAFE.sub("", moment_id or "")[:64] or "moment"
    out = CAPTURES / safe
    out.mkdir(parents=True, exist_ok=True)
    return out


def _capture(payload: dict[str, Any]) -> dict[str, Any]:
    """Decode posted frames, OCR them to text, delete them; return a summary."""
    moment = str(payload.get("moment_id") or f"m{int(time.time())}")
    frames = payload.get("frames") or []
    mdir = _moment_dir(moment)
    fdir = mdir / "frames"
    fdir.mkdir(exist_ok=True)

    paths: list[str] = []
    times: list[float] = []
    for idx, frame in enumerate(frames):
        b64 = str(frame.get("jpg_b64", ""))
        if "," in b64:  # strip a data-URL prefix if present
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError):
            continue
        path = fdir / f"f_{idx}.jpg"
        path.write_bytes(raw)
        paths.append(str(path))
        times.append(float(frame.get("t", idx)))

    summary = perceive_frames(paths, times, str(mdir))
    try:
        fdir.rmdir()
    except OSError:
        pass
    summary["moment_id"] = moment
    return summary


_UNSURE = re.compile(
    r"didn'?t (?:see|read|capture)|don'?t have|do not have|couldn'?t|could not|"
    r"not in (?:my )?memory|i'?m not sure|can'?t tell|cannot tell|no clear|"
    r"didn'?t read enough|i don'?t know", re.I)


def _ask(payload: dict[str, Any]) -> dict[str, Any]:
    """Answer a question over a captured moment via the real brain (ask_home): consensus OCR
    read-or-refuse, the WS1 self/world guard, and honesty gates. Citations come from the
    frames the answer grounded on."""
    moment = str(payload.get("moment_id") or "")
    question = str(payload.get("question") or "").strip()
    mdir = _moment_dir(moment)
    kf = mdir / "kf_memory.json"
    if not kf.exists():
        return {"answer": "Capture a moment first — then ask me about it.",
                "citations": [], "honesty": "unsure"}
    if not question:
        return {"answer": "Ask me something about what you captured.",
                "citations": [], "honesty": "unsure"}

    res = ask_home.ask(question, str(kf), model=MODEL)
    answer = (res.get("answer") or "").strip() if isinstance(res, dict) else str(res)
    scenes = res.get("scenes") or [] if isinstance(res, dict) else []

    seen: set[float] = set()
    cites: list[dict[str, Any]] = []
    for s in scenes:
        t = s.get("t") if isinstance(s, dict) else None
        if t is None or float(t) in seen:
            continue
        seen.add(float(t))
        cites.append({"t_ms": int(float(t) * 1000), "label": f"{float(t):.1f}s"})
    honesty = "unsure" if (not answer or _UNSURE.search(answer)) else "saw_it"
    return {"answer": answer or "I didn't catch that.", "citations": cites[:8], "honesty": honesty}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:  # quiet; we print our own lines
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            try:
                self._send(200, WEB.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"app html missing", "text/plain")
            return
        if self.path == "/cert.pem":
            try:
                self._send(200, CERT.read_bytes(), "application/x-pem-file")
            except OSError:
                self._send(404, b"no cert", "text/plain")
            return
        if self.path == "/api/health":
            self._json(200, {"ok": True, "model": MODEL})
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "bad json"})
            return
        try:
            if self.path == "/api/capture":
                self._json(200, _capture(payload))
            elif self.path == "/api/ask":
                self._json(200, _ask(payload))
            else:
                self._json(404, {"error": "no route"})
        except Exception as exc:  # one failing request must not kill the server
            print(f"  ERR {self.path}: {exc}", file=sys.stderr, flush=True)
            self._json(500, {"error": str(exc)})


def main() -> int:
    if not CERT.exists() or not KEY.exists():
        print(f"missing TLS cert/key at {CERT} — run scripts/make_trace_cert.sh", file=sys.stderr)
        return 2
    CAPTURES.mkdir(parents=True, exist_ok=True)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT), keyfile=str(KEY))
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"TRACE app live on https://localhost:{PORT}  (phone: https://<mac-lan-ip>:{PORT})", flush=True)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
