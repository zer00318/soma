#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from trace_memory.store import TraceMemoryStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--node-types", nargs="*", default=["observation", "entity", "entity_memory", "event_memory", "group_memory"])
    args = parser.parse_args()

    store = TraceMemoryStore(args.store)
    try:
        nodes = store.nodes(node_types=tuple(args.node_types))
    finally:
        store.close()

    payload = []
    for node in nodes:
        payload.append(
            {
                "id": node.id,
                "node_type": node.node_type,
                "text": node.text,
                "source": node.source,
                "helper_type": node.helper_type,
                "t_ms": node.t_ms,
                "coordinate_frame": node.coordinate_frame.to_dict() if node.coordinate_frame else None,
                "time_range": node.time_range.to_dict() if node.time_range else None,
                "spatial_anchor": node.spatial_anchor.to_dict() if node.spatial_anchor else None,
                "source_support": node.source_support,
                "metadata": node.metadata,
                "provenance": node.provenance,
                "derived": node.derived,
                "immutable_raw": node.immutable_raw,
            }
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"exported {len(payload)} nodes to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
