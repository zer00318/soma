#!/usr/bin/env python3
"""Append one event to the cockpit flight recorder (ops/cockpit/activity.jsonl).

Usage:  python scripts/clog.py <kind> <text...>
  kind is a short tag the cockpit colours: ship | fix | run | done | eval | guard |
  commit | note | warn | founder. Anything else renders neutral.

Kept trivially cheap so the Chief can narrate its work in real time:
  python scripts/clog.py run "launched WS2 temporal-binding probe on the day clip"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "ops" / "cockpit" / "activity.jsonl"


def log(kind: str, text: str, ts: int | None = None) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": int(ts if ts is not None else time.time()), "kind": kind, "text": text}
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    log(argv[0], " ".join(argv[1:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
