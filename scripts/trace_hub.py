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
from trace_memory.contract import (  # noqa: E402
    PILLAR_SOURCES,
    helper_id_from_legacy,
    load_registry,
    normalize_fingerprint,
    normalize_grade,
    validate_observation,
)


def helper_of(source: str) -> str:
    """Map the app's per-record `source` to the canonical helper_id. One owner: the
    mapping lives in trace_memory.contract (P02); this name survives for callers."""
    return helper_id_from_legacy(source)


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
        # P41: the timeline gets its OWN reader + lock — /episodes and /digest are the
        # open-the-app surface and must answer in <300ms even while a 30s /ask holds
        # answer_lock. They serve derived rows only; no brain, no gemma.
        self.timeline_lock = threading.Lock()
        self._timeline_store = None
        # P02: the helper registry is DATA (config/helpers.json). Unknown helper_ids
        # still ingest — they surface as "unregistered" in /status, never as a crash.
        self.registry = load_registry()
        self.reject_counts: dict[str, int] = {}
        self.unregistered_seen: set[str] = set()
        self.relocalizations = 0  # P10: count of cross-session anchor re-localizations seen

    def _reader(self) -> TraceMemoryStore:
        if self._answer_store is None:
            self._answer_store = TraceMemoryStore(self.store_path)
        return self._answer_store

    def _timeline_reader(self) -> TraceMemoryStore:
        if self._timeline_store is None:
            self._timeline_store = TraceMemoryStore(self.store_path)
        return self._timeline_store

    def timeline(self, *, kind: str, day: str | None) -> dict:
        """Episode/digest rows for the app's timeline (P41). Derived rows only —
        the memory you can SEE without asking a question. Caller holds timeline_lock."""
        node_type = "digest_day" if kind == "digest" else "episode"
        rows = []
        for n in self._timeline_reader().nodes(node_types=(node_type,)):
            meta = n.metadata or {}
            if day and meta.get("day") != day:
                continue
            row = {
                "id": n.id, "day": meta.get("day"), "text": n.text,
                "start_ms": n.time_range.start_ms if n.time_range else n.t_ms,
                "end_ms": n.time_range.end_ms if n.time_range else n.t_ms,
            }
            if kind == "digest":
                row.update(bullets=meta.get("bullets") or [],
                           thin_day=bool(meta.get("thin_day")),
                           episode_count=meta.get("episode_count"))
            else:
                row.update(kind=meta.get("kind"), label=meta.get("label"),
                           place=meta.get("place"),
                           observation_count=meta.get("observation_count"),
                           channels=meta.get("channels") or {})
            rows.append(row)
        rows.sort(key=lambda r: r["start_ms"], reverse=True)
        return {"ok": True, "kind": kind, "day": day, "count": len(rows), "rows": rows}

    def _record_spatial(self, *, anchor_id, pose, grade, room, session_id, t_ms) -> None:
        """P10: record one place-anchor sighting (cross-session, graded) and count a
        re-localization. Shape-agnostic — the contract path and the legacy phone shape both
        reach the substrate through here, so a row is pinned identically whichever way it
        arrives. Must run under the write lock (the caller holds it)."""
        if not anchor_id:
            return
        rec = self.store.record_anchor(
            str(anchor_id), t_ms=t_ms, session_id=session_id,
            room=room, grade=grade or "none", pose=pose,
        )
        if rec.relocalized:
            self.relocalizations += 1

    @staticmethod
    def _spatial_fields(packet: dict, meta: dict) -> dict:
        """Pull P10 spatial fields from a packet, preferring top-level over metadata, and
        normalize their types so a malformed pose/grade never poisons the row."""
        def pick(key):
            value = packet.get(key)
            return value if value is not None else meta.get(key)
        pose = pick("pose")
        room = pick("room")
        session_id = pick("session_id")
        return {
            "anchor_id": (str(pick("anchor_id")) if pick("anchor_id") else None),
            "pose": pose if isinstance(pose, dict) else None,
            "grade": normalize_grade(pick("grade")),
            "room": (room.strip() if isinstance(room, str) and room.strip() else None),
            "session_id": (str(session_id) if session_id else None),
        }

    def ingest(self, packet: dict) -> dict:
        # P02: two accepted shapes through ONE seam. Contract packets (helper_id/text/
        # t_ms, spec §5) are validated loudly; the phone app's legacy shape (memory_text/
        # source/timestamp) keeps working unchanged.
        if "helper_id" in packet or "contract" in packet:
            return self._ingest_contract(packet)
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
        # P10: the phone streams the legacy shape, so anchor fields ride here too. Absent →
        # nothing changes (exactly today's behavior); present → the row pins like a contract row.
        spatial = self._spatial_fields(packet, meta)
        for key in ("anchor_id", "grade", "room"):
            if spatial[key] and spatial[key] != "none":
                meta.setdefault(key, spatial[key])
        # P11: the appearance fingerprint rides the legacy shape too (stored typed in metadata,
        # never in the text column), so the sleep/live binder can ask "same thing?".
        fingerprint = normalize_fingerprint(packet.get("fingerprint") or meta.get("fingerprint"))
        if fingerprint is not None:
            meta["fingerprint"] = fingerprint
        t_ms = _t_ms(str(packet.get("timestamp") or ""))
        # Live phone rows carry no coordinate_frame, so the canonical helper_type COLUMN would
        # trip validation — the helper identity lives in metadata['helper'].
        self.store.write_observation(
            text=text, t_ms=t_ms,
            source="phone_camera",
            provenance={"source": source, "source_type": packet.get("source_type"),
                        "location_hint": packet.get("location_hint")},
            metadata=meta, pose=spatial["pose"], place=spatial["room"],
        )
        self._record_spatial(t_ms=t_ms, **{k: spatial[k] for k in
                                           ("anchor_id", "pose", "grade", "room", "session_id")})
        self.counts[helper] = self.counts.get(helper, 0) + 1
        return {"ok": True, "helper": helper, "total": sum(self.counts.values())}

    def _ingest_contract(self, packet: dict) -> dict:
        norm, err = validate_observation(packet)
        if err:
            self.reject_counts[err] = self.reject_counts.get(err, 0) + 1
            print(f"  ! contract reject: {err}", flush=True)
            return {"ok": False, "reason": err}
        helper_id = norm["helper_id"]
        entry = self.registry.get(helper_id)
        if entry is None:
            self.unregistered_seen.add(helper_id)
        pillar = str(packet.get("pillar") or (entry or {}).get("pillar") or "phone")
        source = PILLAR_SOURCES.get(pillar, PILLAR_SOURCES["phone"])
        meta = dict(norm["metadata"])
        meta.update({
            "helper": helper_id,
            "helper_prompt": helper_id,
            "contract": 1,
            "registered": entry is not None,
        })
        for key in ("confidence", "anchor_id", "grade", "room", "fingerprint", "session_id"):
            if norm[key] is not None:
                meta[key] = norm[key]
        provenance = dict(norm["provenance"])
        provenance.setdefault("helper_id", helper_id)
        provenance.setdefault("pillar", pillar)
        # P10: pin the row to its place. pose becomes a first-class column (not buried in
        # metadata); room, when the phone relocalized one, becomes the row's `place` so the
        # existing place index serves room-scoped retrieval for free.
        self.store.write_observation(
            text=norm["text"], t_ms=norm["t_ms"], source=source,
            provenance=provenance, metadata=meta,
            pose=norm["pose"], place=norm["room"],
        )
        # P10: the world's memory of the pinned spot itself (cross-session, graded).
        self._record_spatial(
            anchor_id=norm["anchor_id"], pose=norm["pose"], grade=norm["grade"],
            room=norm["room"], session_id=norm["session_id"], t_ms=norm["t_ms"],
        )
        self.counts[helper_id] = self.counts.get(helper_id, 0) + 1
        return {"ok": True, "helper": helper_id, "registered": entry is not None,
                "total": sum(self.counts.values())}

    def store_helper_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.store.nodes(node_types=("observation",), sources=tuple(PILLAR_SOURCES.values())):
            h = (node.metadata or {}).get("helper") or "untagged"
            counts[h] = counts.get(h, 0) + 1
        return counts

    def ask(self, question: str, *, on_event=None) -> dict:
        """Grounded answer + evidence, never an exception (a crash mid-demo is worse than an
        honest error line). The store lock is held through retrieval AND the local-LLM call —
        coarse but correct; asks queue one at a time, /health stays lock-free.
        on_event(stage, info): ask-v2 retrieval narration passthrough (see /ask/stream)."""
        from trace_memory.brain import TraceMemoryAgent
        try:
            agent = TraceMemoryAgent(self._reader(), reasoner="local-ollama",
                                     restrict_sources=tuple(PILLAR_SOURCES.values()))
            a = agent.answer(question, on_event=on_event)
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
            # Carry the FULL evidence row (when · helper · text), not just a flat label — the
            # phone renders expandable receipts identical to the demo page, so "it shows its
            # evidence" is true on the product surface, not only in the browser. `label` stays
            # for older app builds that only decode that field.
            citations = [{"t": None, "label": str(e.get("text", ""))[:120],
                          "when": e.get("when"),
                          "helper": e.get("helper") or e.get("type"),
                          "text": str(e.get("text", ""))[:220]}
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
                coverage = self.hub.store.anchor_coverage()
            return self._send(200, {
                "ok": True, "nodes": nodes, "by_helper": per_helper,
                "registry": sorted(self.hub.registry),
                "unregistered_seen": sorted(self.hub.unregistered_seen),
                "contract_rejects": self.hub.reject_counts,
                "anchors": {
                    "total": coverage["anchors_total"],
                    "relocalized": coverage["anchors_relocalized"],
                    "row_coverage": round(coverage["fraction"], 3),
                    "by_grade": coverage["by_grade"],
                },
            })
        if parsed.path in ("/episodes", "/digest"):
            day = (parse_qs(parsed.query).get("day") or [None])[0]
            kind = "digest" if parsed.path == "/digest" else "episodes"
            with self.hub.timeline_lock:
                return self._send(200, self.hub.timeline(kind=kind, day=day))
        if parsed.path == "/nodes":
            # N1: the entity layer — the companion app browses THINGS, not rows.
            qs = parse_qs(parsed.query)
            etype = (qs.get("type") or [None])[0]
            q = ((qs.get("q") or [""])[0]).lower()
            with self.hub.timeline_lock:
                rows = []
                for n in self.hub._timeline_reader().nodes(node_types=("entity_node",)):
                    meta = n.metadata or {}
                    if etype and meta.get("entity_type") != etype:
                        continue
                    if q and q not in str(meta.get("label", "")).lower() \
                            and q not in n.text.lower():
                        continue
                    rows.append({
                        "id": n.id, "text": n.text,
                        "entity_type": meta.get("entity_type"),
                        "label": meta.get("label"),
                        "sightings": meta.get("sightings"),
                        "attributes": meta.get("attributes") or {},
                        "open_questions": meta.get("open_questions") or [],
                        "first_ms": n.time_range.start_ms if n.time_range else n.t_ms,
                        "last_ms": n.time_range.end_ms if n.time_range else n.t_ms,
                    })
                rows.sort(key=lambda r: r["sightings"] or 0, reverse=True)
            return self._send(200, {"ok": True, "count": len(rows), "rows": rows[:100]})
        if parsed.path == "/ask":
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            if not q:
                return self._send(400, {"ok": False, "reason": "missing q"})
            # answer_lock guards the reader connection + serializes gemma; it does NOT hold
            # write_lock, so ingest keeps flowing while this answer runs.
            with self.hub.answer_lock:
                result = self.hub.ask(q)
            return self._send(200, result)
        if parsed.path == "/ask/stream":
            # Ask-v2: Server-Sent Events. The ~30s local-gemma think must read as WORK,
            # not a hang — retrieval/grounding/thinking events stream as they happen,
            # then one final "answer" event with the same payload /ask returns.
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            if not q:
                return self._send(400, {"ok": False, "reason": "missing q"})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def push(stage: str, info: dict) -> None:
                try:
                    payload = json.dumps({"stage": stage, **info})
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # phone walked away mid-think; the answer still completes

            with self.hub.answer_lock:
                result = self.hub.ask(q, on_event=push)
            push("answer", result)
            return None
        return self._send(404, {"ok": False})


def advertise_bonjour(port: int):
    """Zero-config: advertise this hub as _trace-hub._tcp so the app finds the Mac by
    itself — no one should ever type an IP into a phone (founder, 2026-07-05). The TXT
    record carries the ready-to-use URL (mDNS hostname, valid on any shared network).
    Best-effort: if zeroconf is missing or mDNS is blocked, the hub still serves and the
    app's manual entry (engine room) still works."""
    try:
        import socket
        from zeroconf import ServiceInfo, Zeroconf

        host = socket.gethostname().split(".")[0]
        url = f"http://{host}.local:{port}"
        info = ServiceInfo(
            "_trace-hub._tcp.local.",
            f"TRACE on {host}._trace-hub._tcp.local.",
            port=port,
            properties={"url": url},
            server=f"{host}.local.",
            addresses=[socket.inet_aton(a) for a in _lan_addresses()],
        )
        zc = Zeroconf()
        zc.register_service(info)
        print(f"  Bonjour: advertising {url} as _trace-hub._tcp (app connects itself)")
        return zc
    except Exception as exc:  # noqa: BLE001
        print(f"  Bonjour advertise unavailable ({exc}) — manual hub entry still works")
        return None


def _lan_addresses() -> list:
    import socket
    addrs = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        addrs.add(s.getsockname()[0])
        s.close()
    except Exception:  # noqa: BLE001
        pass
    return list(addrs) or ["127.0.0.1"]


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
    zc = advertise_bonjour(args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        if zc is not None:
            try:
                zc.close()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
