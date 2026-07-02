#!/usr/bin/env python3
"""Probe whether a store contains the critical evidence for the 21Q bedroom demo.

This does NOT score correctness. It answers the pre-question instead:
"Did we even capture the facts needed to answer?"

Usage:
  .venv/bin/python scripts/probe_bedroom_coverage.py --store data/trace_store_frontier.sqlite3
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

CHECKS = [
    ("pesto_flavour", ("peperoncino",)),
    ("fan_mode", ("fan mode 2", "mode 2", "fan mode = 2")),
    ("suitcase_open", ("suitcase", "open")),
    ("blanket_on_suitcase", ("draped over suitcase",)),
    ("mattress_blue", ("mattress/base: blue-grey", "mattress base: blue-grey")),
    ("diary_blue", ("blue booklet", "blue booklet/document")),
    ("water_options", ("white water bottle", "stainless steel cup", "water bottle")),
    ("glasses_seen", ("eyeglasses", "glasses")),
    ("thermal_side_table", ("white water bottle", "stainless steel cup", "nightstand")),
    ("app_claude", ("claude file edit view window help", "app visible:** appears to be **claude")),
    ("app_codex", ("codex file edit view window help",)),
    ("battery_pct", ("100%", "battery percentage")),
    ("microphone_seen", ("microphone",)),
    ("pillows_signal", ("pillow", "pillows")),
    ("jars_count_signal", ("5 nutella", "4 nutella", "3 nutella", "2× nutella", "3× nutella")),
]


def _count_hits(conn: sqlite3.Connection, needle: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM memory_nodes WHERE instr(lower(text), ?) > 0",
        (needle.lower(),),
    ).fetchone()
    return int(row[0] if row else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="data/trace_store_frontier.sqlite3")
    args = ap.parse_args()

    store = Path(args.store)
    if not store.exists():
        raise SystemExit(f"store not found: {store}")

    conn = sqlite3.connect(store)
    try:
        total = conn.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
        links = conn.execute("SELECT COUNT(*) FROM memory_links").fetchone()[0]
        print(f"STORE: {store}")
        print(f"NODES: {total}  LINKS: {links}")

        passed = 0
        for key, needles in CHECKS:
            hits = sum(_count_hits(conn, needle) for needle in needles)
            ok = hits > 0
            if ok:
                passed += 1
            print(f"{'PASS' if ok else 'MISS'}  {key:20s}  hits={hits}")
            for needle in needles:
                count = _count_hits(conn, needle)
                if count:
                    print(f"      - {needle} ({count})")

        print(f"SUMMARY: {passed}/{len(CHECKS)} critical evidence signals present")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
