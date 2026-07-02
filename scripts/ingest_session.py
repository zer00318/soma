#!/usr/bin/env python3
"""ingest_session — the ONE command from capture to a coordinate-bound store.

Feeds a capture directory (frames `*.jpg` + sibling `*.pose.json` + `*.depth.json`)
through the helper swarm + world-coordinate binder (INJECT) into a fresh store of
BOUND entities. This is the main ingestion of the overhaul — no single-caption path.

    .venv/bin/python scripts/ingest_session.py <capture_dir> \
        [--store data/trace_store_demo.sqlite3] [--source phone_camera] [--fresh]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trace_memory.store import TraceMemoryStore, ingest_capture_session  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture_dir")
    ap.add_argument("--store", default="data/trace_store_demo.sqlite3")
    ap.add_argument("--source", default="phone_camera")
    ap.add_argument("--moment", default="")
    ap.add_argument("--fresh", action="store_true", help="delete the store first (clean build)")
    args = ap.parse_args()

    store_path = Path(args.store)
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(store_path) + suffix)
            if p.exists():
                p.unlink()

    moment = args.moment or Path(args.capture_dir).name
    store = TraceMemoryStore(str(store_path))
    try:
        result = ingest_capture_session(store, args.capture_dir, moment_id=moment,
                                        source=args.source)
    finally:
        store.close()

    print(f"BOUND: {len(result.frame_nodes)} frame nodes, "
          f"{len(result.entity_nodes)} ENTITY nodes (distinct world objects), "
          f"{result.link_count} links")
    print(f"confirmed summary: {result.graph_summary[:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
