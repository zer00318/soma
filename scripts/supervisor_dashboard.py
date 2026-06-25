#!/usr/bin/env python3
"""Small local dashboard for the TRACE Claude supervisor."""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path("/Users/zer00/Documents/VLM")
STATE_DIR = ROOT / ".trace_supervisor"
STATE_FILE = STATE_DIR / "state.json"
REQUEST_FILE = STATE_DIR / "USER_TEST_REQUEST.txt"


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TRACE Supervisor</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background:#111827; color:#f3f4f6; margin:0; }
    .wrap { max-width:1100px; margin:0 auto; padding:24px; }
    .row { display:grid; grid-template-columns: repeat(3, 1fr); gap:16px; margin-bottom:16px; }
    .card { background:#1f2937; border:1px solid #374151; border-radius:14px; padding:16px; }
    .wide { grid-column: span 3; }
    .label { color:#9ca3af; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }
    .value { font-size:28px; font-weight:700; margin-top:8px; word-break:break-word; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap; }
    .ok { color:#4ade80; }
    .warn { color:#f59e0b; }
    .bad { color:#f87171; }
    .small { font-size:13px; color:#d1d5db; }
    @media (max-width: 900px) { .row { grid-template-columns:1fr; } .wide { grid-column: span 1; } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>TRACE Supervisor</h1>
    <div class="row">
      <div class="card"><div class="label">Claude process</div><div class="value" id="process">…</div></div>
      <div class="card"><div class="label">Model</div><div class="value" id="model">…</div></div>
      <div class="card"><div class="label">Phase</div><div class="value" id="phase">…</div></div>
    </div>
    <div class="row">
      <div class="card"><div class="label">Last status</div><div class="value" id="status">…</div></div>
      <div class="card"><div class="label">Turns</div><div class="value" id="turns">…</div></div>
      <div class="card"><div class="label">Updated</div><div class="value small" id="updated">…</div></div>
    </div>
    <div class="row">
      <div class="card wide">
        <div class="label">Summary</div>
        <div class="mono small" id="summary">…</div>
      </div>
    </div>
    <div class="row">
      <div class="card wide">
        <div class="label">User test request</div>
        <div class="mono small" id="user_request">None</div>
      </div>
    </div>
    <div class="row">
      <div class="card wide">
        <div class="label">Recent Claude output</div>
        <div class="mono small" id="stdout">…</div>
      </div>
    </div>
    <div class="row">
      <div class="card wide">
        <div class="label">Recent Claude stderr</div>
        <div class="mono small" id="stderr">…</div>
      </div>
    </div>
  </div>
  <script>
    function fmtTs(ts) {
      if (!ts) return "—";
      return new Date(ts * 1000).toLocaleString();
    }
    function setText(id, value) { document.getElementById(id).textContent = value || "—"; }
    async function refresh() {
      const res = await fetch('/api/status');
      const data = await res.json();
      setText('process', data.claude_running ? 'Running' : 'Stopped');
      setText('model', data.state.model);
      setText('phase', data.state.phase);
      setText('status', data.state.last_status);
      setText('turns', String(data.state.turn_count ?? 0));
      setText('updated', fmtTs(data.state.updated_at));
      setText('summary', data.state.last_summary);
      setText('user_request', data.user_test_request || data.state.user_request || 'None');
      setText('stdout', data.recent_stdout);
      setText('stderr', data.recent_stderr);
    }
    refresh();
    setInterval(refresh, 2500);
  </script>
</body>
</html>
"""


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_file(path: str | None, limit: int = 6000) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return text[-limit:]


def claude_running() -> bool:
    proc = subprocess.run(
        ["bash", "-lc", "ps aux | rg 'claude --model|claude_supervisor_loop.py' | rg -v 'rg '"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return bool(proc.stdout.strip())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/status":
            state = load_json(
                STATE_FILE,
                {
                    "model": "fable",
                    "phase": "not_started",
                    "last_status": "unknown",
                    "last_summary": "",
                    "turn_count": 0,
                },
            )
            payload = {
                "claude_running": claude_running(),
                "state": state,
                "user_test_request": REQUEST_FILE.read_text(encoding="utf-8").strip()
                if REQUEST_FILE.exists()
                else "",
                "recent_stdout": read_file(state.get("last_stdout_log")),
                "recent_stderr": read_file(state.get("last_stderr_log")),
            }
            self._json(payload)
            return

        self.send_response(404)
        self.end_headers()


def main() -> int:
    port = int(os.environ.get("TRACE_SUPERVISOR_DASHBOARD_PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TRACE supervisor dashboard: http://127.0.0.1:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
