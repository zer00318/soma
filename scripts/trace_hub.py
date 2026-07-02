#!/usr/bin/env python3
"""TRACE hub — the Mac-side TEXT intake the iOS app streams to, and the ONE demo surface.

The helpers run ON THE PHONE (FastVLM object, Apple Vision OCR, Apple Speech ASR). The app
POSTs each helper's TEXT record to this hub at `/capture/perception` (ContentView.swift).
The Mac receives ONLY text — never re-perceives. This hub:
  - stores every record as an observation tagged with WHICH helper produced it,
  - serves the demo page at `/` (ask box -> grounded answer + evidence + honesty badge),
  - `/ask?q=...` returns the full grounded answer JSON including the evidence chain,
  - `/health` is lock-free so the app's "Brain connected" light NEVER blocks behind a
    slow answer (M7: threaded server + one store lock; sqlite is not thread-safe shared).

    .venv/bin/python scripts/trace_hub.py [--store data/trace_store.sqlite3] [--port 8765]
On the phone: tap the brain icon -> set hub to  http://<this-mac-ip>:8765
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trace_memory.store import TraceMemoryStore  # noqa: E402


def helper_of(source: str) -> str:
    """Map the app's per-record `source` to the canonical helper aspect."""
    s = (source or "").lower()
    if s.startswith("fastvlm") or s == "vlm":
        return "vlm_object"
    if "vision" in s or "ocr" in s:
        return "ocr"
    if "speech" in s or "whisper" in s or "asr" in s:
        return "asr"
    if "detector" in s or s == "native":
        return "detector"
    return "vlm_object"


def _t_ms(timestamp: str) -> int:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return int(datetime.strptime(timestamp, fmt).timestamp() * 1000)
        except (ValueError, TypeError):
            continue
    return int(time.time() * 1000)


class Hub:
    def __init__(self, store_path: str) -> None:
        self.store_path = store_path
        self.store = TraceMemoryStore(store_path)      # WRITER — ingest only
        self.counts: dict[str, int] = {}
        # ThreadingHTTPServer gives every request its own thread. sqlite connections are not
        # thread-safe to share, so each of the two connections has its own lock:
        #  - write_lock guards the writer (ingest); held only for the fast store write.
        #  - answer_lock guards a SEPARATE reader connection used to answer questions, and also
        #    serializes the GPU-serial gemma call. Because the reader is a different connection
        #    (WAL mode), a 30s answer no longer blocks the phone's frame uploads — the M7 coarse
        #    single-lock made every capture POST wait behind the in-flight /ask (measured 16.5s).
        self.write_lock = threading.Lock()
        self.answer_lock = threading.Lock()
        self._answer_store = None  # lazily opened reader connection

    def _reader(self) -> TraceMemoryStore:
        if self._answer_store is None:
            self._answer_store = TraceMemoryStore(self.store_path)
        return self._answer_store

    def ingest(self, packet: dict) -> dict:
        text = str(packet.get("memory_text") or packet.get("raw_text") or "").strip()
        if not text:
            return {"ok": False, "reason": "empty text"}
        source = str(packet.get("source") or "unknown")
        helper = helper_of(source)
        meta = dict(packet.get("metadata") or {})
        meta.update({
            "helper": helper,
            "helper_prompt": helper,
            "source_type": packet.get("source_type"),
            "scene_phase": packet.get("scene_phase"),
            "active_entity_labels": packet.get("active_entity_labels"),
            "section_kind": "physical_object",
        })
        # Live phone rows carry no coordinate_frame, so the canonical helper_type COLUMN would
        # trip validation — the helper identity lives in metadata['helper'].
        self.store.write_observation(
            text=text, t_ms=_t_ms(str(packet.get("timestamp") or "")),
            source="phone_camera",
            provenance={"source": source, "source_type": packet.get("source_type"),
                        "location_hint": packet.get("location_hint")},
            metadata=meta,
        )
        self.counts[helper] = self.counts.get(helper, 0) + 1
        return {"ok": True, "helper": helper, "total": sum(self.counts.values())}

    def store_helper_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.store.nodes(node_types=("observation",), sources=("phone_camera",)):
            h = (node.metadata or {}).get("helper") or "untagged"
            counts[h] = counts.get(h, 0) + 1
        return counts

    def ask(self, question: str) -> dict:
        """Grounded answer + evidence, never an exception (a crash mid-demo is worse than an
        honest error line). The store lock is held through retrieval AND the local-LLM call —
        coarse but correct; asks queue one at a time, /health stays lock-free."""
        from trace_memory.brain import TraceMemoryAgent
        try:
            agent = TraceMemoryAgent(self._reader(), reasoner="local-ollama",
                                     restrict_sources=("phone_camera",))
            a = agent.answer(question)
            evidence = [
                {"when": r.get("when"), "helper": r.get("helper_prompt") or r.get("helper_type"),
                 "type": r.get("type"), "text": str(r.get("text", ""))[:220]}
                for r in a.evidence_chain[:9]
            ]
            badge = "refused" if a.refused else ("firm" if a.confidence >= 0.7 else "hedged")
            return {"ok": True, "question": question, "answer": a.answer,
                    "confidence": a.confidence, "refused": a.refused, "badge": badge,
                    "mode": a.retrieval_mode, "evidence": evidence}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "question": question,
                    "answer": "The brain hit an internal error answering this.",
                    "error": str(exc)[:200], "refused": True, "badge": "error",
                    "confidence": 0.0, "evidence": []}


_DEMO_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRACE — ask your memory</title><style>
body{font-family:-apple-system,system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;background:#0f1115;color:#e8eaf0}
h1{font-size:1.3rem;font-weight:600} .sub{color:#8a90a0;font-size:.85rem;margin-bottom:1.2rem}
#q{width:100%;font-size:1.05rem;padding:.7rem .9rem;border-radius:10px;border:1px solid #2a2f3a;background:#171a21;color:#e8eaf0;box-sizing:border-box}
#ans{margin-top:1.2rem;font-size:1.15rem;line-height:1.5;min-height:1.5em}
.badge{display:inline-block;padding:.15rem .6rem;border-radius:999px;font-size:.75rem;margin-left:.5rem;vertical-align:middle}
.firm{background:#123d24;color:#5ed08a}.hedged{background:#3d3312;color:#e0c05e}.refused{background:#2a2f3a;color:#9aa2b5}.error{background:#3d1212;color:#e05e5e}
#ev{margin-top:1rem;border-top:1px solid #2a2f3a;padding-top:.8rem}
.row{font-size:.82rem;color:#9aa2b5;padding:.3rem 0;border-bottom:1px dashed #22262f}
.row b{color:#c6cbd8;font-weight:500}.when{color:#5e86d0;margin-right:.5rem}.helper{color:#8a5ed0;margin-right:.5rem}
.spin{color:#8a90a0;font-size:.9rem} .stats{font-size:.75rem;color:#5a6070;margin-top:2rem}
</style></head><body>
<h1>TRACE <span class="sub">— ask what it remembers. It shows its evidence, and it refuses what it didn't see.</span></h1>
<input id="q" placeholder="Ask: where is… / how many… / what did I say about…" autofocus>
<div id="ans"></div><div id="ev"></div><div class="stats" id="stats"></div>
<script>
const q=document.getElementById('q'),ans=document.getElementById('ans'),ev=document.getElementById('ev'),stats=document.getElementById('stats');
q.addEventListener('keydown',async e=>{
 if(e.key!=='Enter'||!q.value.trim())return;
 ans.innerHTML='<span class="spin">thinking (local brain, unhurried)…</span>';ev.innerHTML='';
 try{
  const r=await fetch('/ask?q='+encodeURIComponent(q.value.trim()));const d=await r.json();
  ans.innerHTML=escapeHtml(d.answer)+' <span class="badge '+d.badge+'">'+d.badge+' · '+(d.confidence??0).toFixed(2)+'</span>';
  ev.innerHTML=(d.evidence||[]).map(r=>'<div class="row"><span class="when">'+(r.when||'')+'</span><span class="helper">'+(r.helper||r.type||'')+'</span><b>'+escapeHtml(r.text||'')+'</b></div>').join('');
 }catch(err){ans.innerHTML='<span class="badge error">connection error</span>';}
});
function escapeHtml(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
fetch('/status').then(r=>r.json()).then(d=>{stats.textContent='store: '+d.nodes+' memories · '+Object.entries(d.by_helper||{}).map(([k,v])=>k+' '+v).join(' · ');});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    hub: Hub = None  # set on the server instance

    def _send(self, code: int, obj, ctype="application/json") -> None:
        body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quieter
        pass

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"

        # The iOS app POSTs /ask with {"question": ...} and decodes {answer, source, refused,
        # citations, model}. (GET /ask?q= is the browser path.) Serve BOTH so the app works.
        if parsed.path == "/ask":
            try:
                body = json.loads(raw)
            except Exception:
                body = {}
            q = str(body.get("question") or body.get("q") or "").strip()
            if not q:
                # AskResult.answer is required — never return a body missing it, or the app
                # throws "the data couldn't be read because it is missing".
                return self._send(200, {"answer": "Please ask a question.", "refused": True,
                                        "source": "empty", "citations": [], "model": "trace"})
            with self.hub.answer_lock:
                result = self.hub.ask(q)
            citations = [{"t": None, "label": str(e.get("text", ""))[:120]}
                         for e in result.get("evidence", [])]
            return self._send(200, {
                "answer": result.get("answer", "I don't know"),
                "refused": bool(result.get("refused")),
                "source": result.get("mode", "trace"),
                "citations": citations,
                "model": "local-gemma",
                "confidence": result.get("confidence", 0.0),
                "badge": result.get("badge", ""),
            })

        if not parsed.path.startswith("/capture/perception"):
            return self._send(404, {"ok": False, "reason": "unknown path"})
        try:
            packet = json.loads(raw)
        except Exception:
            return self._send(400, {"ok": False, "reason": "bad json"})
        with self.hub.write_lock:
            result = self.hub.ingest(packet)
        if result.get("ok"):
            snippet = str(packet.get("memory_text") or "")[:70].replace("\n", " ")
            print(f"  + [{result['helper']:10}] {snippet}   (total {result['total']})", flush=True)
        return self._send(200, result)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            # Lock-free on purpose: the app's "Brain connected" light and the demo page's
            # liveness must never wait behind a slow answer.
            return self._send(200, {"ok": True, "service": "trace-hub"})
        if parsed.path == "/":
            return self._send(200, _DEMO_PAGE, ctype="text/html; charset=utf-8")
        if parsed.path == "/status":
            with self.hub.write_lock:
                per_helper = dict(self.hub.store_helper_counts())
                nodes = self.hub.store.node_count()
            return self._send(200, {"ok": True, "nodes": nodes, "by_helper": per_helper})
        if parsed.path == "/ask":
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            if not q:
                return self._send(400, {"ok": False, "reason": "missing q"})
            # answer_lock guards the reader connection + serializes gemma; it does NOT hold
            # write_lock, so ingest keeps flowing while this answer runs.
            with self.hub.answer_lock:
                result = self.hub.ask(q)
            return self._send(200, result)
        return self._send(404, {"ok": False})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="data/trace_store.sqlite3")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    Handler.hub = Hub(args.store)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"TRACE hub listening on http://0.0.0.0:{args.port}  store={args.store}")
    print("  GET  /                    (demo page: ask -> answer + evidence + honesty badge)")
    print("  POST /capture/perception  (app streams helper text here)")
    print("  GET  /ask?q=...           (grounded answer JSON with evidence)")
    print("  set the app's hub (brain icon) to  http://<this-mac-ip>:%d" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
