#!/usr/bin/env python3
"""Analyze a perception worker log for the all-day budget proof.

    python3 scripts/analyze_budget_run.py /tmp/soma_budget_run.json

Reports per-hour enrichment counts vs the ceiling, salience distribution,
and scheduler counters — the moat metric is steady all-day operation with
the budget never exceeded and salient moments still caught.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])

    ticks = 0
    requests: list[dict] = []
    first_ts = last_ts = None
    for line in path.open(encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        ts = obj.get("timestamp_utc", "")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        if obj.get("type") == "perception_tick":
            ticks += 1
        elif obj.get("type") == "enrichment_request":
            requests.append(obj)

    if not first_ts:
        print("No parseable events in log.")
        return 1

    per_hour = Counter(r["timestamp_utc"][:13] for r in requests)
    saliences = sorted(r.get("salience", 0.0) for r in requests)

    print(f"run window : {first_ts} .. {last_ts}")
    print(f"ticks      : {ticks}")
    print(f"enrichments: {len(requests)}")
    print("\nper hour (UTC):")
    for hour in sorted(per_hour):
        print(f"  {hour}:00  {per_hour[hour]}")
    if saliences:
        mid = saliences[len(saliences) // 2]
        print(f"\nsalience  min={saliences[0]:.3f} median={mid:.3f} max={saliences[-1]:.3f}")
    if requests:
        s = requests[-1].get("stats", {})
        print(
            f"final counters: enriched={s.get('enriched')} denied={s.get('budget_denied')} "
            f"below_threshold={s.get('below_threshold')} evicted={s.get('evicted_stale')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
