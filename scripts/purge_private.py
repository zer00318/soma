#!/usr/bin/env python3
"""P43-lite: owner-invoked purge of private rows (founder order 2026-07-05).

The never-delete law protects memories from the SYSTEM deciding to forget;
owner-requested deletion is the spec'd exception (W4 P43 hide-then-purge).
This applies config/privacy_blocklist.json retroactively: any raw row whose
text matches a marker is deleted, along with links touching it and any
derived row that cites it in its bullets/members.

Safety: sqlite .backup of the store FIRST (data/purge_backups/), then delete,
then print counts. --dry-run lists matches without touching anything.

  .venv/bin/python scripts/purge_private.py --dry-run
  .venv/bin/python scripts/purge_private.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "trace_store.sqlite3"
BACKUP_DIR = ROOT / "data" / "purge_backups"
BLOCKLIST = ROOT / "config" / "privacy_blocklist.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--store", default=str(STORE))
    args = ap.parse_args()

    markers = [m.lower() for m in json.loads(BLOCKLIST.read_text())["markers"]]
    import sqlite3
    con = sqlite3.connect(args.store)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, t_ms, substr(text,1,80) AS head, lower(text) AS lt "
                       "FROM memory_nodes").fetchall()
    hits = [r for r in rows if any(m in r["lt"] for m in markers)]
    print(f"blocklist markers: {len(markers)} · store rows: {len(rows)} · matches: {len(hits)}")
    for r in hits:
        when = datetime.fromtimestamp(r["t_ms"] / 1000).strftime("%m-%d %H:%M")
        print(f"  {when}  {r['head']}")
    if args.dry_run or not hits:
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"pre_purge.{stamp}.sqlite3"
    subprocess.run(["sqlite3", args.store, f".backup '{backup}'"], check=True, timeout=300)
    print(f"backup: {backup}")

    ids = [r["id"] for r in hits]
    for node_id in ids:
        con.execute("DELETE FROM memory_links WHERE from_id=? OR to_id=?", (node_id, node_id))
        con.execute("DELETE FROM memory_nodes WHERE id=?", (node_id,))
    # derived rows that cite a purged id inside their metadata (digest bullets,
    # episode members) — rebuilt clean by the next nightly anyway, purge now.
    derived = con.execute("SELECT id, metadata_json FROM memory_nodes WHERE derived=1").fetchall()
    cited = [d["id"] for d in derived if any(i in (d["metadata_json"] or "") for i in ids)]
    for node_id in cited:
        con.execute("DELETE FROM memory_links WHERE from_id=? OR to_id=?", (node_id, node_id))
        con.execute("DELETE FROM memory_nodes WHERE id=?", (node_id,))
    con.commit()
    print(f"purged: {len(ids)} raw rows + {len(cited)} derived rows citing them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
