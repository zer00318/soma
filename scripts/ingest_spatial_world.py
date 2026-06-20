#!/usr/bin/env python3
"""Post a pulled spatial_world.json to the hub as a spatial word-map snapshot.

Recovery tool for the silent-loss class: the app's spatial snapshot post is
fire-and-forget (no spool), so a scan done while the phone cannot reach the
hub leaves /world empty even though the device world file is fine. This
replays the device truth into the hub using the same payload shape the app
posts (SpatialWorld.postSpatialSnapshotIfNeeded).

Usage: python3 scripts/ingest_spatial_world.py <spatial_world.json> \
        [--hub http://127.0.0.1:8765] [--build SHA]
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("world_json")
    ap.add_argument("--hub", default="http://127.0.0.1:8765")
    ap.add_argument("--build", default="replay")
    args = ap.parse_args()

    objects = json.load(open(args.world_json))
    if not objects:
        print("world file is empty; nothing to ingest")
        return 1

    captured_at = max((o.get("lastSeen") or "" for o in objects), default="")
    if not captured_at:
        captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    spatial_words = []
    labels = []
    lines = []
    for o in objects:
        label = o.get("label") or "?"
        labels.append(label)
        lines.append(f"OBJECT | {label} | mobileclip spatial object | spatial word map | likely")
        spatial_words.append({
            "label": label,
            "kind": "object",
            "x": round(float(o.get("x", 0.0)), 2),
            "y": round(float(o.get("y", 0.0)), 2),
            "z": round(float(o.get("z", 0.0)), 2),
            "w": round(float(o.get("w", 0.0)), 2),
            "h": round(float(o.get("h", 0.0)), 2),
            "strength": int(o.get("sightings", 1)),
            "footprint": o.get("footprint") if isinstance(o.get("footprint"), list) else [],
            "heightM": round(float(o.get("heightM", 0.0)), 2),
        })

    payload = {
        "timestamp": captured_at,
        "source_type": "vision",
        "source": "mobileclip_spatial_word",
        "provider": "mobileclip_spatial_word",
        "scene_phase": "spatial_word_map",
        "confidence": 0.75,
        "stability_count": 2,
        "active_entity_labels": labels,
        "memory_text": "\n".join(lines),
        "metadata": {
            "capture_mode": "spatial_word_map",
            "spatial_words": spatial_words,
            "tracking_state": "replayed_from_device_pull",
            "word_source": "mobileclip_zero_shot",
            "scanner_output": "",
            "build": args.build,
        },
    }
    req = urllib.request.Request(
        f"{args.hub}/capture/perception",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-SOMA-Token": "dev-token"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"hub {resp.status}: {len(spatial_words)} words "
              f"({', '.join(sorted(set(labels)))}) captured_at={captured_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
