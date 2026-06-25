#!/usr/bin/env python3
"""Night-shift cockpit — watch the local-LLM workforce in a browser.

http://localhost:8788 — live task board (queue + statuses), worker log,
founder-request panel with a DONE button (no terminal needed), and
restart/stop controls for the shift. BaseHTTPRequestHandler only (no
Flask, project constraint); polls every 3s.

Run:  nohup python3 scripts/night_shift_dashboard.py > /dev/null 2>&1 &
"""
from __future__ import annotations

import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path("/Users/zer00/Documents/VLM")
QUEUE = ROOT / "ops" / "night_shift_queue.json"
STATE = ROOT / "ops" / "night_shift_state.json"
LOG = Path("/tmp/trace_night_shift.log")
REQUEST = Path("/tmp/trace_founder_request.txt")
REPLY = Path("/tmp/trace_founder_reply.txt")
PORT = 8788

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TRACE Night Shift</title>
<style>
 body{background:#0d1117;color:#e6edf3;font:14px -apple-system,sans-serif;margin:0;padding:24px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#8b949e;margin-bottom:20px}
 .row{display:flex;gap:20px;flex-wrap:wrap}
 .col{flex:1;min-width:340px}
 .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin-bottom:12px}
 .task{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;margin-bottom:6px;background:#0d1117}
 .dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
 .done{background:#3fb950}.running{background:#d29922;animation:pulse 1.2s infinite}
 .failed{background:#f85149}.pending{background:#30363d}
 @keyframes pulse{50%{opacity:.3}}
 .kind{color:#8b949e;font-size:11px;margin-left:auto}
 pre{background:#010409;border-radius:8px;padding:10px;font-size:11.5px;white-space:pre-wrap;
     max-height:380px;overflow-y:auto;color:#7ee787}
 .req{border-color:#d29922;background:#1c1610}
 button{background:#238636;color:#fff;border:0;border-radius:8px;padding:10px 22px;
        font-size:15px;font-weight:600;cursor:pointer;margin-right:8px}
 button.gray{background:#30363d}button.red{background:#da3633}
 .badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600}
 .alive{background:#1b4721;color:#3fb950}.dead{background:#4c1512;color:#f85149}
 .bar{height:10px;background:#21262d;border-radius:6px;overflow:hidden;margin:8px 0 4px}
 .fill{height:100%;background:linear-gradient(90deg,#1f6feb,#3fb950);transition:width .6s}
</style></head><body>
<h1>TRACE Night Shift <span id="alive" class="badge dead">checking…</span></h1>
<div class="sub">Local models working while everyone sleeps · refreshes every 3s</div>
<div class="row">
 <div class="col">
  <div class="card"><b>Pipeline</b><div class="bar"><div id="fill" class="fill" style="width:0%"></div></div>
   <div id="tasks"></div>
   <div style="margin-top:10px">
     <button class="gray" onclick="act('restart')">↻ Restart shift</button>
     <button class="red" onclick="act('stop')">■ Stop</button>
   </div>
  </div>
  <div class="card req" id="reqcard" style="display:none">
    <b>🙋 The workers need YOU</b>
    <pre id="reqtext" style="color:#e3b341"></pre>
    <button onclick="act('done')">✅ I did it — continue</button>
  </div>
 </div>
 <div class="col"><div class="card"><b>Worker log</b><pre id="log"></pre></div></div>
</div>
<script>
async function act(a){await fetch('/api/'+a,{method:'POST'});refresh()}
async function refresh(){
 const r = await (await fetch('/api/state')).json();
 document.getElementById('alive').textContent = r.alive ? 'RUNNING' : 'STOPPED';
 document.getElementById('alive').className = 'badge ' + (r.alive ? 'alive' : 'dead');
 const st = r.state.tasks || {};
 let done = 0;
 document.getElementById('tasks').innerHTML = r.queue.map(t=>{
   const s = (st[t.id]||{}).status || 'pending';
   if(s==='done') done++;
   return `<div class="task"><span class="dot ${s}"></span>${t.title}
           <span class="kind">${t.kind}${s==='failed'?' · FAILED':''}</span></div>`;
 }).join('');
 document.getElementById('fill').style.width = (100*done/r.queue.length)+'%';
 document.getElementById('log').textContent = r.log;
 const rq = document.getElementById('reqcard');
 if(r.request){rq.style.display='block';document.getElementById('reqtext').textContent=r.request}
 else rq.style.display='none';
}
refresh();setInterval(refresh,3000);
</script></body></html>"""


def shift_alive() -> bool:
    return subprocess.run(["pgrep", "-f", "trace_night_shift.py"],
                          capture_output=True).returncode == 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def _send(self, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            queue = json.loads(QUEUE.read_text()).get("tasks", [])
            state = json.loads(STATE.read_text()) if STATE.exists() else {"tasks": {}}
            log = LOG.read_text()[-6000:] if LOG.exists() else "(no log yet)"
            request = REQUEST.read_text() if REQUEST.exists() and not REPLY.exists() else None
            # only surface the request while the shift is actually waiting
            waiting = any(v.get("status") == "running" for v in state["tasks"].values())
            self._send(json.dumps({
                "alive": shift_alive(),
                "queue": [{"id": t["id"], "title": t["title"], "kind": t["kind"]} for t in queue],
                "state": state,
                "log": log,
                "request": request if (request and waiting) else None,
            }).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/done":
            REPLY.write_text("done\n")
        elif self.path == "/api/stop":
            subprocess.run(["pkill", "-f", "trace_night_shift.py"], capture_output=True)
        elif self.path == "/api/restart":
            subprocess.run(["pkill", "-f", "trace_night_shift.py"], capture_output=True)
            # failed tasks become retryable on restart
            if STATE.exists():
                state = json.loads(STATE.read_text())
                for tid, st in state["tasks"].items():
                    if st.get("status") == "failed":
                        st["status"] = "pending"
                STATE.write_text(json.dumps(state, indent=2))
            subprocess.Popen(
                ["nohup", "python3", str(ROOT / "scripts" / "trace_night_shift.py")],
                stdout=open("/tmp/trace_night_shift_stdout.log", "a"),
                stderr=subprocess.STDOUT, cwd=ROOT, start_new_session=True,
            )
        self._send(b'{"ok": true}')


if __name__ == "__main__":
    print(f"night-shift cockpit: http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
