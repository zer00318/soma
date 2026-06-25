#!/usr/bin/env python3
"""Post a fused offline walk world into the TRACE hub.

Positioned objects are sent with metadata.spatial_words so the existing
spatial_pose graph path persists them. Positionless objects are still posted
as object inventory for recall, but intentionally omit spatial_words.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any


def _load_world(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {"schema": "walk_world.v1", "objects": raw}
    if not isinstance(raw, dict):
        raise ValueError("walk world must be a JSON object or list")
    objects = raw.get("objects")
    if not isinstance(objects, list):
        raise ValueError("walk world JSON must contain an objects list")
    return raw


def _float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positioned(obj: dict[str, Any]) -> bool:
    return all(_float_or_none(obj.get(axis)) is not None for axis in ("x", "y", "z"))


def _trust(obj: dict[str, Any]) -> str:
    trust = str(obj.get("trust") or "trusted").strip().lower()
    return "rejected" if trust == "rejected" else "trusted"


def _name_source(obj: dict[str, Any]) -> str:
    return str(obj.get("name_source") or "").strip() or "unknown"


def _confidence(obj: dict[str, Any]) -> float:
    value = _float_or_none(obj.get("confidence"))
    if value is None:
        return 0.65
    return max(0.0, min(1.0, value))


def payloads_from_world(world: dict[str, Any], timestamp: str | None = None) -> list[dict[str, Any]]:
    captured_at = timestamp or str(world.get("generated_at") or "") or datetime.now(timezone.utc).isoformat()
    payloads: list[dict[str, Any]] = []
    for obj in world.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        label = " ".join(str(obj.get("label") or "").split())
        if not label:
            continue
        count = max(1, int(obj.get("count") or 1))
        depth_mode = str(obj.get("depth_mode") or "none")
        evidence = obj.get("frame_evidence") if isinstance(obj.get("frame_evidence"), list) else []
        confidence = _confidence(obj)
        trust = _trust(obj)
        name_source = _name_source(obj)
        offline_inventory = {
            "label": label,
            "count": count,
            "confidence": confidence,
            "depth_mode": depth_mode,
            "frame_evidence": [str(path) for path in evidence],
            "trust": trust,
            "name_source": name_source,
            "trusted_count": int(obj.get("trusted_count") or 0),
            "rejected_count": int(obj.get("rejected_count") or 0),
        }
        metadata: dict[str, Any] = {
            "capture_mode": "offline_walk",
            "source": "offline_walk",
            "provider": "offline_walk",
            "walk_world_schema": str(world.get("schema") or "walk_world.v1"),
            "pose_mode": str(world.get("pose_mode") or ""),
            "offline_inventory": offline_inventory,
            "depth_mode": depth_mode,
            "trust": trust,
            "name_source": name_source,
        }
        if trust == "trusted" and _positioned(obj):
            x = _float_or_none(obj.get("x"))
            y = _float_or_none(obj.get("y"))
            z = _float_or_none(obj.get("z"))
            metadata["spatial_words"] = [
                {
                    "label": label,
                    "kind": "object",
                    "x": x,
                    "y": y,
                    "z": z,
                    "strength": count,
                    "sightings": count,
                    "verified": False,
                    "position_confidence": "inferred",
                    "depth_mode": depth_mode,
                    "source": "offline_walk",
                    "trust": trust,
                    "name_source": name_source,
                }
            ]
        likelihood = "likely" if trust == "trusted" else "untrusted"
        payloads.append(
            {
                "timestamp": captured_at,
                "source_type": "vision",
                "source": "offline_walk",
                "provider": "offline_walk",
                "scene_phase": "offline_walk",
                "confidence": confidence,
                "stability_count": count,
                "memory_text": f"OBJECT | {label} | offline walk fusion | {depth_mode} | {likelihood}",
                "metadata": metadata,
            }
        )
    return payloads


def _post_json(url: str, token: str, payload: dict[str, Any]) -> tuple[int, str]:
    req = urllib.request.Request(
        url.rstrip("/") + "/capture/perception",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-TRACE-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", default="/tmp/walk_world.json")
    parser.add_argument("--hub", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default="dev-token")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    world = _load_world(args.world)
    payloads = payloads_from_world(world)
    if args.dry_run:
        print(json.dumps({"payloads": payloads}, indent=2, sort_keys=True))
        return 0

    ok = 0
    for payload in payloads:
        status, _body = _post_json(args.hub, args.token, payload)
        if 200 <= status < 300:
            ok += 1
        else:
            print(f"post failed {status}: {payload.get('memory_text')}", file=sys.stderr)
    positioned = sum(1 for payload in payloads if payload.get("metadata", {}).get("spatial_words"))
    print(f"posted {ok}/{len(payloads)} offline_walk objects ({positioned} positioned) to {args.hub}")
    return 0 if ok == len(payloads) else 1


if __name__ == "__main__":
    sys.exit(main())
