#!/usr/bin/env python
"""Fast binder iteration: re-run the world-grounded binder over an ALREADY-perceived store
without re-perceiving (which costs ~10 min + frontier API). Copies src -> dst, strips any
prior authored memories + binder links, then runs the new SleepConsolidator.

    .venv/bin/python scripts/rebind_store.py --src data/trace_store_frontier.sqlite3 \
        --dst data/trace_store_rebind.sqlite3 [--deterministic] [--max-llm N]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time

from trace_memory.store import TraceMemoryStore
from trace_memory.store.author import deterministic_author
from trace_memory.store.sleep import SleepConsolidator

_AUTHORED = ("entity_memory", "group_memory", "event_memory", "composed_memory", "abstraction")
_BINDER_LINKS = ("supports_memory", "supersedes", "candidate_same_memory")


def _strip_prior(path: str) -> tuple[int, int]:
    con = sqlite3.connect(path)
    cur = con.cursor()
    q = ",".join("?" for _ in _AUTHORED)
    n_nodes = cur.execute(f"DELETE FROM memory_nodes WHERE node_type IN ({q})", _AUTHORED).rowcount
    ql = ",".join("?" for _ in _BINDER_LINKS)
    n_links = cur.execute(f"DELETE FROM memory_links WHERE link_type IN ({ql})", _BINDER_LINKS).rowcount
    con.commit()
    con.close()
    return n_nodes, n_links


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--deterministic", action="store_true", help="skip the LLM, rule-based authoring only")
    ap.add_argument("--max-llm", type=int, default=60)
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    args = ap.parse_args()

    shutil.copyfile(args.src, args.dst)
    dn, dl = _strip_prior(args.dst)
    print(f"[rebind] stripped {dn} prior authored nodes, {dl} binder links from {args.dst}")

    store = TraceMemoryStore(args.dst)
    if args.deterministic:
        author = deterministic_author
    else:
        from trace_memory.store.author import LocalLLMAuthor
        author = LocalLLMAuthor(model=args.model)

    t0 = time.time()
    summary = SleepConsolidator(store, author=author, max_llm_clusters=args.max_llm).consolidate()
    dt = time.time() - t0

    authored = store.nodes(node_types=_AUTHORED)
    llm = sum(1 for n in authored if (n.metadata or {}).get("authored_by") == "local_llm")
    with_loc = sum(1 for n in authored if (n.metadata or {}).get("current_location"))
    with_count = sum(1 for n in authored if (n.metadata or {}).get("count") is not None)
    print(f"[rebind] {dt:.0f}s  authored={len(authored)} (llm={llm})  "
          f"with_current_location={with_loc}  with_count={with_count}  links={summary.link_count}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
