#!/usr/bin/env python3
"""S1 — build a CLEAN demo store from the polluted unified store.

ROOT CAUSE this fixes: the unified store is ~79% self-homework pollution — `mac_screen`
capture of YouTube + the Claude / Codex / cockpit windows (us discussing the founder's own
questions), which then gets retrieved as "memory" and drives confident-wrong answers.

For the bedroom demo (21 founder questions) NONE of the answers live in mac_screen — the
laptop-screen facts (Codex app, 100% battery) are seen by the PHONE camera. So the clean demo
store keeps real lived-experience sources and drops the screen-capture pollution entirely.

    .venv/bin/python scripts/build_demo_store.py
        [--src data/trace_store.sqlite3] [--out data/trace_store_demo.sqlite3]

Validation it self-runs: prints before/after counts, asserts 0 denylist residue, asserts the
phone_camera signal is preserved 1:1, and re-probes the bedroom keywords by source.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# Real lived-experience sources kept verbatim. Everything else (mac_screen dev/entertainment)
# is dropped for the demo corpus.
KEEP_SOURCES = ("phone_camera", "phys_video", "native_speech", "live_screen")
# Belt-and-suspenders: even within kept sources, never keep a node that is clearly a captured
# dev/entertainment SCREEN (in case a screen leaked in under another source label).
DENYLIST_TOKENS = (
    "SCREEN [Claude]", "SCREEN [Codex]", "SCREEN [Cockpit]", "SCREEN [Terminal]",
    "SCREEN [Brave", "SCREEN [Microsoft Edge]", "SCREEN [Google Chrome]", "SCREEN [Safari]",
    "youtube.com", "youtu.be",
)


def _counts_by_source(conn: sqlite3.Connection) -> dict[str, int]:
    return {row[0]: row[1] for row in conn.execute(
        "SELECT source, COUNT(*) FROM memory_nodes GROUP BY source ORDER BY 2 DESC")}


def build(src: Path, out: Path) -> int:
    if not src.exists():
        print(f"FATAL: source store {src} not found", file=sys.stderr)
        return 2
    shutil.copy2(src, out)
    conn = sqlite3.connect(out)
    try:
        before = _counts_by_source(conn)
        phone_before = before.get("phone_camera", 0)

        placeholders = ",".join("?" for _ in KEEP_SOURCES)
        # Drop every node not in the kept lived-experience sources.
        conn.execute(
            f"DELETE FROM memory_nodes WHERE source NOT IN ({placeholders})", KEEP_SOURCES)
        # Drop any leaked dev/entertainment screen nodes inside kept sources.
        for token in DENYLIST_TOKENS:
            conn.execute("DELETE FROM memory_nodes WHERE text LIKE ?", (f"%{token}%",))
        # Drop links whose endpoints no longer exist.
        conn.execute(
            "DELETE FROM memory_links WHERE from_id NOT IN (SELECT id FROM memory_nodes) "
            "OR to_id NOT IN (SELECT id FROM memory_nodes)")
        conn.commit()

        after = _counts_by_source(conn)
        phone_after = after.get("phone_camera", 0)
        nodes_after = conn.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
        links_after = conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]

        # Self-validation (machine-checked, not vibes).
        residue = 0
        for token in DENYLIST_TOKENS:
            residue += conn.execute(
                "SELECT COUNT(*) FROM memory_nodes WHERE text LIKE ?", (f"%{token}%",)).fetchone()[0]
        mac_residue = conn.execute(
            "SELECT COUNT(*) FROM memory_nodes WHERE source='mac_screen'").fetchone()[0]

        print(f"SOURCE store: {sum(before.values())} nodes  {before}")
        print(f"DEMO   store: {nodes_after} nodes, {links_after} links  {after}")
        print(f"DENYLIST RESIDUE: {residue}")
        print(f"MAC_SCREEN RESIDUE: {mac_residue}")
        print(f"PHONE_CAMERA preserved: {phone_after}/{phone_before}")
        for kw in ("nutella", "fan", "pillow", "suitcase"):
            rows = list(conn.execute(
                "SELECT source, COUNT(*) FROM memory_nodes WHERE lower(text) LIKE ? GROUP BY source",
                (f"%{kw}%",)))
            print(f"  {kw:10s}: {rows}")

        ok = residue == 0 and phone_after == phone_before
        print("VALIDATION:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/trace_store.sqlite3")
    ap.add_argument("--out", default="data/trace_store_demo.sqlite3")
    args = ap.parse_args()
    return build(Path(args.src), Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
