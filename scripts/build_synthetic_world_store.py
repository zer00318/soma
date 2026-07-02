#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from trace_memory.store import SleepConsolidator, TraceMemoryStore, observation_time_range  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="ops/fixtures/world_grounded/sample_binder_inputs.json")
    parser.add_argument("--store", default="ops/fixtures/world_grounded/synthetic_binder_store.sqlite3")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--export", default="ops/fixtures/world_grounded/binder_outputs.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    store_path = Path(args.store)
    export_path = Path(args.export)
    payload = json.loads(input_path.read_text())

    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(store_path) + suffix)
            if candidate.exists():
                candidate.unlink()

    store = TraceMemoryStore(str(store_path))
    try:
        coordinate_frame = dict(payload.get("coordinate_frame") or {})
        observations = list(payload.get("observations") or [])
        for row in observations:
            t_ms = int(row["t_ms"])
            store.write_canonical_observation(
                text=str(row["text"]),
                t_ms=t_ms,
                source="fixture.synthetic",
                helper_type=str(row["helper_type"]),
                coordinate_frame=coordinate_frame,
                time_range=observation_time_range(t_ms),
                spatial_anchor=dict(row["spatial_anchor"]),
                provenance={"fixture_id": row["id"]},
                source_support={"fixture_ids": [row["id"]]},
                metadata=dict(row.get("metadata") or {}),
                immutable_raw=True,
            )
        summary = SleepConsolidator(store).consolidate()
        nodes = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
    finally:
        store.close()

    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(
            {
                "summary": {
                    "grouped_observation_count": summary.grouped_observation_count,
                    "abstraction_count": summary.abstraction_count,
                    "composed_memory_count": summary.composed_memory_count,
                    "link_count": summary.link_count,
                },
                "memories": [
                    {
                        "id": node.id,
                        "node_type": node.node_type,
                        "text": node.text,
                        "support_ids": node.metadata.get("support_ids") or [],
                        "subject_hint": node.metadata.get("subject_hint"),
                        "memory_kind": node.metadata.get("memory_kind"),
                    }
                    for node in nodes
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"built synthetic store {store_path} and exported binder outputs to {export_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
