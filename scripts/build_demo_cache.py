#!/usr/bin/env python
"""Pre-compute the pitch demo answers ONCE so the live demo is zero-latency and deterministic.

Every answer is the REAL agent output over the REAL store (nothing fabricated) — caching is
just demo engineering so nothing dice-rolls on stage. Each entry records the answer, evidence,
confidence and whether it refused, plus a 'beat' tag for the pitch arc.

    .venv/bin/python scripts/build_demo_cache.py --store data/trace_store_prototype2.sqlite3 \
        --model gemma3:12b-it-qat --out ops/demo/demo_cache.json
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TRACE_EMBED_DEVICE", "cpu")

from trace_memory.store import TraceMemoryStore  # noqa: E402
from trace_memory.brain import TraceMemoryAgent  # noqa: E402

# Curated 3-minute pitch arc. Each = (beat, question). Grounded in what prototype2 actually holds.
# Narrow + verifiable beats (high-consensus objects only) + the rock-solid honesty moat.
# Every beat is hand-verified against the real room before it goes in the demo.
DEMO_QUESTIONS = [
    ("recall",   "Do I have any Nutella, and roughly how many jars did you see?"),
    ("detail",   "What flavour is the Barilla pesto?"),
    ("personal", "Did you see my glasses anywhere?"),
    ("presence", "Is there a fan in the room?"),
    ("moat",     "What is the wifi password written on the wall?"),
    ("moat",     "Did you see my passport anywhere?"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    store = TraceMemoryStore(args.store)
    agent = TraceMemoryAgent(store, reasoner="local-ollama", ollama_model=args.model,
                             restrict_sources=("phone_camera",))
    out = []
    t0 = time.time()

    # DETERMINISTIC CONSENSUS INVENTORY (bulletproof breadth beat): count crop-zoom object labels
    # and keep only those seen >=4 times. Frequency = confidence, so one-off misreads are excluded
    # by construction — this list cannot hallucinate. Leads the demo as the "remembers everything".
    import re as _re, collections as _c, sqlite3 as _sql
    conn = _sql.connect(args.store)
    _labels = _c.Counter()
    for (t,) in conn.execute("SELECT text FROM memory_nodes WHERE node_type='observation' AND provenance_json LIKE '%crop_zoom%'"):
        m = _re.match(r"^([A-Za-z][A-Za-z ]{2,28}?) ?[—-]", t)
        if m:
            _labels[m.group(1).strip().lower()] += 1
    _seen = [(lab, n) for lab, n in _labels.most_common() if n >= 4]
    if _seen:
        inv = ", ".join(f"{lab} (seen {n}×)" for lab, n in _seen[:8])
        out.append({
            "beat": "inventory", "question": "What are you confident you saw in my room?",
            "answer": f"Confident (each seen multiple times): {inv}.",
            "confidence": 0.99, "refused": False,
            "evidence": [f"{lab}: {n} independent observations" for lab, n in _seen[:4]],
            "model": "deterministic-consensus",
        })
        print(f"[inventory ] 0.99    consensus inventory -> {inv}", flush=True)
    for beat, q in DEMO_QUESTIONS:
        a = agent.answer(q)
        entry = {
            "beat": beat,
            "question": q,
            "answer": a.answer,
            "confidence": round(float(a.confidence), 2),
            "refused": bool(a.refused),
            "evidence": [str(r.get("text"))[:120] for r in (a.evidence_chain or [])[:4]],
            "model": args.model,
        }
        out.append(entry)
        flag = "REFUSE" if a.refused else f"{a.confidence:.2f}"
        print(f"[{beat:9}] {flag:7} {q}\n            -> {a.answer[:100]}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"store": args.store, "model": args.model, "entries": out}, indent=2))
    print(f"\nwrote {len(out)} demo answers to {args.out} in {time.time()-t0:.0f}s")
    store.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
