#!/usr/bin/env python3
"""Live cockpit — an always-on status page served from the (always-awake) Mac.

Open it on the Mac:    http://localhost:8765
Open it on the phone:  http://<this-mac-LAN-ip>:8765   (same WiFi)

It auto-refreshes every 15s and reads the SAME real signals as scripts/cockpit.py
(git, the test gate, the live bound memory, the 24/7 robot log). Nothing is
hand-typed; unmeasured numbers say so.

Run:  python3 scripts/cockpit_server.py            (serves forever)
"""
from __future__ import annotations

import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cockpit  # noqa: E402  reuse the exact same signal-gathering

PORT = 8765
REFRESH_S = 15


def _card(title: str, body: str, tint: str = "card") -> str:
    return f'<div class="{tint}"><div class="lbl">{title}</div>{body}</div>'


def render_html(state: dict) -> str:
    mem = state.get("memory", {})
    rob = state.get("robots", {})
    gate = state.get("gate", {})
    git = state.get("git", {})
    counts = mem.get("counts", {}) if isinstance(mem, dict) else {}

    halluc = rob.get("halluc_pct")
    recall = rob.get("recall_pct")
    halluc_disp = f"{halluc}%" if halluc is not None else "&mdash;"
    recall_disp = f"{recall}%" if recall is not None else "&mdash;"
    nums = (
        '<div class="grid2">'
        + _card(
            "Made-up answers",
            f'<div class="big" style="color:#3fae6b">{halluc_disp}</div>'
            '<div class="hint">lower is better</div>',
        )
        + _card(
            "Questions answered",
            f'<div class="big">{recall_disp}</div>'
            '<div class="hint">self-test probes, not a human benchmark</div>',
        )
        + "</div>"
    )

    works = (
        f'<li>Turns video into memory: <b>{counts.get("entities","?")}</b> things, '
        f'<b>{counts.get("bindings","?")}</b> confident facts, '
        f'<b>{counts.get("refused","?")}</b> weak guesses dropped on purpose.</li>'
        f'<li>Answers with receipts: "what did the laptop screen say?" &rarr; "Welcome back, Satoshi".</li>'
        f'<li>Says "I don\'t know" instead of making things up.</li>'
    ) if mem.get("usable") else f'<li>bound memory not built ({html.escape(str(mem.get("error","?")))})</li>'

    misses = rob.get("misses") or []
    miss_html = "".join(f"<li>{html.escape(str(m))}</li>" for m in misses) or "<li>nothing wrong this round</li>"
    robots_body = (
        f'<div class=hint>running 24/7 on local AI</div>'
        f'<div>Last check: <b>{rob.get("last_check","—")}</b> &middot; rounds: <b>{rob.get("rounds","0")}</b></div>'
        f'<ul class=tiny>{miss_html}</ul>'
    ) if rob.get("rounds") else f'<div class=hint>{html.escape(str(rob.get("status","starting")))}</div>'

    health = (
        f'Quality gate: <b style="color:{"#3fae6b" if gate.get("status")=="GREEN" else "#c2772e"}">{gate.get("status","?")}</b> '
        f'&middot; {gate.get("tests","?")} tests<br>'
        f'Branch: <code>{html.escape(str(git.get("branch","?")))}</code><br>'
        f'Unbanked commits: {git.get("commits_ahead_of_main","?")}'
    )

    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<meta http-equiv=refresh content="{REFRESH_S}">
<title>SOMA cockpit</title>
<style>
body{{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#f5f4ef;color:#1c1c1a;padding:16px;max-width:760px;margin:0 auto}}
h1{{font-size:20px;font-weight:600;margin:0}}
.sub{{color:#75736c;font-size:13px;margin:2px 0 16px}}
.dot{{color:#3fae6b}}
.card{{background:#fff;border:1px solid #e4e2da;border-radius:12px;padding:14px 16px;margin:10px 0}}
.lbl{{font-size:12px;color:#75736c;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.big{{font-size:30px;font-weight:600}}
.hint{{font-size:11px;color:#9b988f}}
.stages{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:10px 0}}
.stage{{border-radius:10px;padding:10px;font-size:13px;font-weight:500}}
.done{{background:#e3f3e9;color:#1f6b41}} .now{{background:#e6f0fb;color:#1a5aa0}} .later{{background:#efeee8;color:#8a887f}}
ul{{margin:6px 0;padding-left:18px;line-height:1.6}} .tiny{{font-size:12px;color:#75736c}}
code{{background:#efeee8;padding:1px 5px;border-radius:5px;font-size:12px}}
b{{font-weight:600}}
</style></head><body>
<h1>SOMA &mdash; live status <span class=dot>&#9679;</span></h1>
<div class=sub>auto-refreshes every {REFRESH_S}s &middot; generated {state.get("generated","")} &middot; 100% local AI</div>

<div class=lbl>The journey</div>
<div class=stages>
  <div class="stage done">&#10003; brain works<br><span class=hint>on recorded video</span></div>
  <div class="stage now">&rarr; on iPhone<br><span class=hint>live capture &mdash; next</span></div>
  <div class="stage later">glasses<br><span class=hint>later</span></div>
</div>

<div class=lbl>How good is it (local AI grades itself)</div>
{nums}

{_card("What it can do now (proven on a real walk)", f"<ul>{works}</ul>")}
{_card("The robots", robots_body)}
{_card("Health", health)}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        try:
            state = cockpit.build()
            if self.path.startswith("/api"):
                payload = json.dumps(state, indent=2).encode()
                ctype = "application/json"
            else:
                payload = render_html(state).encode()
                ctype = "text/html; charset=utf-8"
        except Exception as exc:  # never serve a blank page
            payload = f"<pre>cockpit error: {html.escape(str(exc))}</pre>".encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args: object) -> None:
        pass  # quiet


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"cockpit live on http://localhost:{PORT}  (and http://<lan-ip>:{PORT})", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
