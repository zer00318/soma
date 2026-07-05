"""3-day-scale readiness probe (async — no device, no carrying).

Builds a multi-day store from REAL rows (the live store's content, time-shifted across
3 synthetic days and multiplied to carry-scale volume), then measures what the founder
would hit on day 3:
  - /ask wall-clock latency per question class (the answer_lock serializes asks — a slow
    answer IS the product experience),
  - honesty invariants at scale (refusal on absent, counts stay ranged, no crash),
  - multi-day temporal semantics ("yesterday", "this morning", ordering).

Usage:  .venv/bin/python evaluation/scale_probe_3day.py [--mult 5]
Never touches the live store: works on a copy under evaluation/ras/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

LIVE = ROOT / "data" / "trace_store.sqlite3"
PROBE = ROOT / "evaluation" / "ras" / "scale_probe_3day.sqlite3"
DAY_MS = 24 * 3600 * 1000

QUESTIONS = [
    ("count", "how many bottles did I see?"),
    ("existence", "did I see a laptop?"),
    ("absent-refusal", "how many unicorns are on the desk?"),
    ("temporal-yesterday", "what did I see yesterday?"),
    ("temporal-order", "did I see the laptop before the bed?"),
    ("speech", "what did I say about the washing machine?"),
    ("where", "where is the laptop?"),
]


def build(mult: int) -> int:
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    if PROBE.exists():
        PROBE.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(PROBE) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy(LIVE, PROBE)
    con = sqlite3.connect(PROBE)
    cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(memory_nodes)").fetchall()]
    ins_cols = [c for c in cols if c not in ("seq",)]
    rows = cur.execute(
        f"SELECT {', '.join(ins_cols)} FROM memory_nodes"
    ).fetchall()
    id_idx = ins_cols.index("id")
    t_idx = ins_cols.index("t_ms")
    meta_idx = ins_cols.index("metadata_json")
    n = 0
    # Shift real rows back 1 and 2 days, `mult` copies per day with per-copy suffixed ids
    # and session ids, so cross-day rows are distinct sessions (as real days would be).
    for day in (1, 2):
        for copy_i in range(mult):
            for row in rows:
                r = list(row)
                r[id_idx] = f"{row[id_idx]}-d{day}c{copy_i}"
                r[t_idx] = int(row[t_idx]) - day * DAY_MS - copy_i * 60_000
                try:
                    meta = json.loads(r[meta_idx])
                    if isinstance(meta, dict):
                        sid = meta.get("anchor_id")
                        if sid:
                            meta["anchor_id"] = f"{sid}-d{day}c{copy_i}"
                        if meta.get("track_id"):
                            meta["track_id"] = f"{meta['track_id']}-d{day}c{copy_i}"
                        r[meta_idx] = json.dumps(meta)
                except (TypeError, ValueError):
                    pass
                cur.execute(
                    f"INSERT INTO memory_nodes ({', '.join(ins_cols)}) "
                    f"VALUES ({', '.join('?' for _ in ins_cols)})",
                    r,
                )
                n += 1
    con.commit()
    total = cur.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
    con.close()
    return total


def probe() -> list[dict]:
    from trace_memory.brain import TraceMemoryAgent
    from trace_memory.store import TraceMemoryStore

    store = TraceMemoryStore(PROBE)
    agent = TraceMemoryAgent(store, reasoner="local-ollama")
    out = []
    for kind, q in QUESTIONS:
        t0 = time.time()
        try:
            a = agent.answer(q)
            dt = time.time() - t0
            out.append({
                "kind": kind, "q": q, "seconds": round(dt, 1),
                "answer": a.answer[:160], "confidence": a.confidence,
                "refused": a.refused,
            })
        except Exception as exc:  # noqa: BLE001
            out.append({"kind": kind, "q": q, "seconds": round(time.time() - t0, 1),
                        "error": str(exc)[:200]})
        print(json.dumps(out[-1]), flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mult", type=int, default=5)
    ap.add_argument("--skip-build", action="store_true")
    args = ap.parse_args()
    if not args.skip_build:
        t0 = time.time()
        total = build(args.mult)
        print(f"probe store: {total} rows (built in {time.time()-t0:.1f}s)", flush=True)
    results = probe()
    worst = max((r.get("seconds", 0) for r in results), default=0)
    errors = [r for r in results if r.get("error")]
    print(f"\nWORST ask latency: {worst}s · errors: {len(errors)}", flush=True)


if __name__ == "__main__":
    main()
