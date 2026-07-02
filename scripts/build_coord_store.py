#!/usr/bin/env python
"""Re-anchor an existing crop-zoom store to WORLD COORDINATES (no gemma re-perceive), then bind.

The perception (gemma reads) is already in the source store; this only adds geometry: each
crop-zoom instance's 2D box + its frame's depth/pose -> a world-aligned XYZ (world_point anchor).
The coordinate-aware binder then individuates same-label observations into distinct physical
instances and authors a deterministic count. This is the cheap path to "the brain counts 5".

    .venv/bin/python scripts/build_coord_store.py --src data/trace_store_prototype2.sqlite3 \
        --capture data/phone_captures/bedroom_dense_353f --dst data/trace_store_coord.sqlite3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world_project import instance_world_xyz  # noqa: E402

from trace_memory.store import TraceMemoryStore  # noqa: E402
from trace_memory.store.sleep import SleepConsolidator  # noqa: E402
from trace_memory.store.author import deterministic_author  # noqa: E402
from trace_memory.store.world import world_point_anchor  # noqa: E402


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--capture", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--llm", action="store_true", help="use the local-LLM author (default: deterministic, fast)")
    args = ap.parse_args()

    cap = Path(args.capture)
    src = TraceMemoryStore(args.src)
    Path(args.dst).unlink(missing_ok=True)
    dst = TraceMemoryStore(args.dst)

    wh_cache: dict[str, tuple[int, int]] = {}
    reanchored = copied = 0
    for n in src.nodes(node_types=("observation",)):
        prov = n.provenance or {}
        anchor = n.spatial_anchor.to_dict() if n.spatial_anchor else None
        meta = dict(n.metadata or {})
        box = prov.get("box")
        frame = prov.get("frame")
        if prov.get("crop_zoom") and box and frame:
            depth = _load(cap / frame.replace(".jpg", ".depth.json"))
            pose = _load(cap / frame.replace(".jpg", ".pose.json"))
            if frame not in wh_cache:
                try:
                    wh_cache[frame] = Image.open(cap / frame).size
                except Exception:
                    wh_cache[frame] = (1440, 1920)
            xyz = instance_world_xyz(box, wh_cache[frame], depth, pose)
            if xyz:
                anchor = world_point_anchor(xyz).to_dict()
                meta["world_xyz"] = list(xyz)
                reanchored += 1
        else:
            copied += 1
        if n.coordinate_frame is None or anchor is None:
            continue
        dst.write_canonical_observation(
            text=n.text, t_ms=n.t_ms, source=n.source, helper_type=n.helper_type or "vlm_object",
            coordinate_frame=n.coordinate_frame.to_dict(), spatial_anchor=anchor,
            time_range=n.time_range.to_dict() if n.time_range else None,
            provenance=prov, source_support=n.source_support or {}, place=n.place, pose=n.pose,
            metadata=meta, immutable_raw=True,
        )

    print(f"[coord] reanchored {reanchored} crop-zoom obs to world_point; copied {copied}")
    author = None if args.llm else deterministic_author
    summary = SleepConsolidator(dst, author=author).consolidate()
    print(f"[coord] authored {summary.abstraction_count} memories, {summary.link_count} links")
    src.close(); dst.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
