"""Nightly consolidation for the 3-day carry (3-day-carry blocker #2).

Before this, the sleep binder had NEVER run automatically — every consolidation was a
manual chief action, so a day-2 problem would surface at day 3. This job makes each
night a checkpoint:

  1. BACKUP the live store (dated copy; keeps the last 7) — if consolidation ever
     corrupts, the previous night is one `cp` away.
  2. RUN SleepConsolidator on the live store (reconsiders its own derived output,
     re-authors from immutable raw — safe to re-run).
  3. VERIFY with the canonical battery — exit-1 on any confident-wrong, so a poisoned
     night is loud, not silent.
  4. LOG one summary line to evaluation/nightly_log.jsonl.

Install (runs 03:30 while the Mac is awake — see ops/RUNBOOK_3DAY.md for caffeinate):
  30 3 * * * cd /Users/zer00/Documents/VLM && .venv/bin/python scripts/nightly_sleep.py >> /tmp/trace_nightly.log 2>&1
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

STORE = ROOT / "data" / "trace_store.sqlite3"
BACKUP_DIR = ROOT / "data" / "nightly_backups"
LOG = ROOT / "evaluation" / "nightly_log.jsonl"
KEEP_BACKUPS = 7


def backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"trace_store.{stamp}.sqlite3"
    # sqlite3 .backup is consistent even with the hub running (WAL); plain cp risks a
    # mid-write copy.
    subprocess.run(
        ["sqlite3", str(STORE), f".backup '{dest}'"], check=True, timeout=300
    )
    backups = sorted(BACKUP_DIR.glob("trace_store.*.sqlite3"))
    for old in backups[:-KEEP_BACKUPS]:
        old.unlink()
    return dest


def consolidate() -> dict:
    from trace_memory.store import EpisodeBuilder, TraceMemoryStore
    from trace_memory.store.digest import DigestBuilder
    from trace_memory.store.sleep import SleepConsolidator

    store = TraceMemoryStore(STORE)
    summary = SleepConsolidator(store).consolidate()
    episodes = EpisodeBuilder(store).build()
    digests = DigestBuilder(store).build()
    return {
        "grouped": summary.grouped_observation_count,
        "abstractions": summary.abstraction_count,
        "composed": summary.composed_memory_count,
        "links": summary.link_count,
        "episodes": episodes.episode_count,
        "gaps": episodes.gap_count,
        "episode_days": episodes.day_count,
        "digest_days": digests.day_count,
        "thin_days": digests.thin_day_count,
    }


def battery() -> int:
    r = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"),
         str(ROOT / "evaluation" / "run_canonical_battery.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    tail = "\n".join(r.stdout.splitlines()[-10:])
    print(tail, flush=True)
    return r.returncode


def main() -> None:
    t0 = time.time()
    entry: dict = {"at": datetime.now().isoformat(timespec="seconds")}
    try:
        dest = backup()
        entry["backup"] = dest.name
        entry["sleep"] = consolidate()
        entry["battery_rc"] = battery()
        entry["ok"] = entry["battery_rc"] == 0
    except Exception as exc:  # noqa: BLE001
        entry["ok"] = False
        entry["error"] = str(exc)[:300]
    entry["seconds"] = round(time.time() - t0, 1)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(json.dumps(entry), flush=True)
    sys.exit(0 if entry.get("ok") else 1)


if __name__ == "__main__":
    main()
