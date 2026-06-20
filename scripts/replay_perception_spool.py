#!/usr/bin/env python3
"""Replay an offline perception spool through the real ingest path.

M1 (worn-POV walk): outdoors the iPhone has no route to the Mac hub, so the
app appends every undeliverable perception packet to
Application Support/SOMA/perception_spool.ndjson. After the walk:

  1. Pull the spool from the device (phone unlocked, cable attached):
     xcrun devicectl device copy from \
       --device D3A506B2-8923-5313-B8A3-FF769ABBA228 \
       --domain-type appDataContainer --domain-identifier de.zer00.soma \
       --source "Library/Application Support/SOMA/perception_spool.ndjson" \
       --destination /tmp/perception_spool.ndjson

  2. Replay (timestamps are preserved — ingest_packet honors the packet's
     own 'timestamp', so graph rows carry walk-time, not replay-time):
     python3 scripts/replay_perception_spool.py /tmp/perception_spool.ndjson

For large replays, stop the hub/enricher daemons first to avoid SQLite
write contention (pkill -f soma_hub.api; pkill -f soma_perception.enricher).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soma_hub.service import SomaHub  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spool", help="ndjson spool file pulled from the device")
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    args = parser.parse_args()

    hub = SomaHub(Path(args.data_dir))
    ingested = skipped = failed = 0
    entities = events = observations = 0

    lines = Path(args.spool).read_text().splitlines()
    # Spool is append-ordered, but sort by packet time anyway: encounter and
    # liveness logic assume chronological arrival.
    packets: list[dict] = []
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            print(f"  line {n}: unparseable, skipped", file=sys.stderr)
            skipped += 1
            continue
        if not str(payload.get("memory_text") or payload.get("text") or "").strip():
            skipped += 1  # diagnostics entries, not perception packets
            continue
        packets.append(payload)
    packets.sort(key=lambda p: str(p.get("timestamp") or p.get("captured_at") or ""))

    for payload in packets:
        try:
            result = hub.ingest_perception(payload)
        except Exception as exc:
            print(f"  ingest failed ({exc}): {str(payload)[:120]}", file=sys.stderr)
            failed += 1
            continue
        ingested += 1
        graph = result.get("graph") or result  # service returns graph counts
        entities += int(graph.get("entities") or 0)
        events += int(graph.get("events") or 0)
        observations += int(graph.get("observations") or 0)

    print(
        f"replayed {ingested} packets ({skipped} skipped, {failed} failed) → "
        f"{entities} entity upserts, {events} events, {observations} observations"
    )
    if ingested and not failed:
        print(f"spool fully ingested — safe to delete on device and locally")


if __name__ == "__main__":
    main()
