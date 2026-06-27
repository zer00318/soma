from __future__ import annotations

import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_memory.store.sqlite_store import TraceMemoryStore

_PITCH_BUCKET_DEGREES = 15
_YAW_BUCKET_DEGREES = 15


@dataclass(frozen=True)
class ShelfIngestResult:
    frame_nodes: tuple[str, ...]
    entity_nodes: tuple[str, ...]
    link_count: int
    graph_summary: str


@dataclass(frozen=True)
class KfIngestResult:
    observation_nodes: tuple[str, ...]
    entity_nodes: tuple[str, ...]
    link_count: int


def _frame_number(path: Path) -> float:
    return float(path.stem)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text())


def _pose_degrees(pose: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pose:
        return None
    result: dict[str, Any] = dict(pose)
    for key in ("yaw", "pitch", "roll"):
        value = pose.get(key)
        if isinstance(value, (int, float)):
            result[f"{key}_deg"] = round(float(value) * 180.0 / math.pi, 2)
    return result


def _place_bucket(pose: dict[str, Any] | None) -> str | None:
    if not pose:
        return None
    yaw = pose.get("yaw_deg")
    pitch = pose.get("pitch_deg")
    if not isinstance(yaw, (int, float)) or not isinstance(pitch, (int, float)):
        return None
    yaw_bucket = int(round(float(yaw) / _YAW_BUCKET_DEGREES) * _YAW_BUCKET_DEGREES)
    pitch_bucket = int(round(float(pitch) / _PITCH_BUCKET_DEGREES) * _PITCH_BUCKET_DEGREES)
    return f"yaw:{yaw_bucket}|pitch:{pitch_bucket}"


def _instance_line(instance: dict[str, Any]) -> str:
    parts = [
        str(instance.get("type") or "object"),
        str(instance.get("label") or "").strip(),
    ]
    for text in instance.get("texts") or ():
        if text and text not in parts:
            parts.append(str(text))
    attrs = instance.get("attrs") or {}
    for key in ("state", "colour", "color", "material"):
        value = attrs.get(key)
        if value:
            parts.append(f"{key}={value}")
    return " | ".join(bit for bit in parts if bit and bit != "None")


def _frame_summary(frame_path: Path, instances: list[dict[str, Any]]) -> str:
    lines = [f"frame {frame_path.name}"]
    for instance in instances:
        name = str(instance.get("name") or instance.get("det_label") or "object").strip()
        text = str(instance.get("text") or "").strip()
        state = str(instance.get("state") or "").strip()
        colour = str(instance.get("colour") or "").strip()
        parts = [name]
        if text and text.upper() != "NONE":
            parts.append(f"text={text}")
        if state and state.lower() != "unknown":
            parts.append(f"state={state}")
        if colour and colour.lower() != "unknown":
            parts.append(f"colour={colour}")
        lines.append(" - " + ", ".join(parts))
    return "\n".join(lines)


def _entity_summary(entity: dict[str, Any]) -> str:
    lines = [f"entity {_instance_line(entity)}"]
    frames = entity.get("frames") or []
    if frames:
        lines.append("seen_in_frames=" + ",".join(str(frame) for frame in frames))
    world_xyz = entity.get("world_xyz")
    if world_xyz:
        lines.append(
            "world_xyz=" + ",".join(f"{float(value):.3f}" for value in world_xyz)
        )
    return " | ".join(lines)


def ingest_validated_shelf(
    store: TraceMemoryStore,
    capture_dir: str | Path,
    *,
    moment_id: str = "validated_shelf_20260627",
    max_instances: int = 12,
) -> ShelfIngestResult:
    os.environ.setdefault("TRACE_GROUNDING_DINO_MAX_INSTANCES", str(max_instances))
    capture_path = Path(capture_dir)
    frame_paths = sorted(capture_path.glob("*.jpg"), key=_frame_number)
    if not frame_paths:
        raise FileNotFoundError(f"no jpg frames under {capture_path}")

    import scripts.instance_brain_wire as instance_brain_wire

    graphs_store: dict[str, dict[str, Any]] = {}
    raw_frames: list[list[dict[str, Any]]] = []
    pose_rows: list[dict[str, Any] | None] = []
    frame_nodes: list[str] = []
    links = 0

    for frame_index, frame_path in enumerate(frame_paths):
        pose = _pose_degrees(_load_json(frame_path.with_suffix(".pose.json")))
        depth_grid = _load_json(frame_path.with_suffix(".depth.json"))
        graph = instance_brain_wire.perceive_and_graph(
            str(frame_path),
            moment_id,
            graphs_store,
            pose=pose,
            depth_grid=depth_grid,
        )
        instances = list((graph.get("_frame_instances") or [[]])[-1] or [])
        raw_frames.append(instances)
        pose_rows.append(pose)

        t_ms = int(round(_frame_number(frame_path) * 1000))
        place = _place_bucket(pose)
        node = store.write_observation(
            text=_frame_summary(frame_path, instances),
            t_ms=t_ms,
            source="validated_shelf.frame",
            place=place,
            pose=pose,
            provenance={
                "moment_id": moment_id,
                "frame_path": str(frame_path),
                "pose_path": str(frame_path.with_suffix(".pose.json")),
                "depth_path": str(frame_path.with_suffix(".depth.json")),
            },
            metadata={
                "frame_index": frame_index,
                "frame_name": frame_path.name,
                "instances": instances,
            },
        )
        frame_nodes.append(node.id)
        if frame_index:
            store.link(frame_nodes[frame_index - 1], node.id, "succession")
            links += 1

    final_graph = graphs_store.get(moment_id) or {}
    consolidated = (final_graph.get("consolidated") or {}).get("instances") or []
    entity_nodes: list[str] = []
    frames_by_place: defaultdict[str, list[str]] = defaultdict(list)
    for node_id, pose in zip(frame_nodes, pose_rows):
        bucket = _place_bucket(pose)
        if bucket:
            frames_by_place[bucket].append(node_id)

    for frame_ids in frames_by_place.values():
        for left, right in zip(frame_ids, frame_ids[1:]):
            store.link(left, right, "same_place")
            links += 1

    entity_support: defaultdict[int, list[str]] = defaultdict(list)
    for entity in consolidated:
        frames = [int(index) for index in (entity.get("frames") or []) if isinstance(index, int)]
        first_frame = min(frames) if frames else 0
        frame_path = frame_paths[min(first_frame, len(frame_paths) - 1)]
        pose = pose_rows[min(first_frame, len(pose_rows) - 1)]
        place = _place_bucket(pose)
        entity_node = store.write_observation(
            text=_entity_summary(entity),
            t_ms=int(round(_frame_number(frame_path) * 1000)),
            source="validated_shelf.entity",
            place=place,
            pose=pose,
            provenance={
                "moment_id": moment_id,
                "builder": "world_binder",
                "frame_support": frames,
            },
            metadata=entity,
            node_type="entity",
        )
        entity_nodes.append(entity_node.id)
        for frame_index in frames:
            if 0 <= frame_index < len(frame_nodes):
                store.link(entity_node.id, frame_nodes[frame_index], "same_entity")
                links += 1
                entity_support[frame_index].append(entity_node.id)

    for supported_entities in entity_support.values():
        for index, left in enumerate(supported_entities):
            for right in supported_entities[index + 1 :]:
                store.link(left, right, "same_time")
                links += 1

    return ShelfIngestResult(
        frame_nodes=tuple(frame_nodes),
        entity_nodes=tuple(entity_nodes),
        link_count=links,
        graph_summary=str((final_graph.get("consolidated") or {}).get("summary_confirmed") or ""),
    )


_INSTANCE_LINE_RE = re.compile(
    r'^\s*#(?P<index>\d+)\s+(?P<type>[a-z0-9_-]+)(?:\s+"(?P<label>[^"]+)")?(?P<rest>.*)$',
    re.IGNORECASE,
)


def _parse_instance_block(caption: str) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for raw_line in caption.splitlines():
        if raw_line.strip().startswith("SPATIAL RELATIONS"):
            break
        match = _INSTANCE_LINE_RE.match(raw_line)
        if not match:
            continue
        rest = match.group("rest") or ""
        if " is " in rest and "colour=" not in rest and "material=" not in rest and "state=" not in rest and "orient=" not in rest and 'text="' not in rest:
            continue
        attrs = {
            key.lower(): value.strip()
            for key, value in re.findall(r"([a-zA-Z_]+)=([^=]+?)(?=\s+[a-zA-Z_]+=|$)", rest)
        }
        text_match = re.search(r'text="([^"]+)"', rest)
        parsed.append(
            {
                "index": int(match.group("index")),
                "type": match.group("type"),
                "label": (match.group("label") or "").strip(),
                "text": text_match.group(1).strip() if text_match else "",
                "attrs": attrs,
            }
        )
    return parsed


def ingest_kf_memory(
    store: TraceMemoryStore,
    kf_path: str | Path,
    *,
    moment_id: str = "kf_memory",
    source_prefix: str = "derived_kf",
) -> KfIngestResult:
    import json

    path = Path(kf_path)
    rows = json.loads(path.read_text())
    observation_nodes: list[str] = []
    entity_nodes: list[str] = []
    links = 0

    previous_observation_id: str | None = None
    for index, row in enumerate(rows):
        caption = str(row.get("caption") or "").strip()
        if not caption:
            continue
        metadata = dict(row)
        pose = metadata.get("pose") if isinstance(metadata.get("pose"), dict) else None
        place = None
        location_hint = str(metadata.get("location_hint") or "").strip()
        if location_hint:
            place = location_hint.split("|", 1)[-1].strip()
        observation = store.write_observation(
            text=caption,
            t_ms=int(round(float(row.get("t") or 0.0) * 1000)),
            source=f"{source_prefix}.observation",
            place=place,
            pose=pose,
            provenance={
                "moment_id": moment_id,
                "frame": row.get("frame"),
                "source": row.get("source"),
                "scene": row.get("scene"),
            },
            metadata=metadata,
        )
        observation_nodes.append(observation.id)
        if previous_observation_id is not None:
            store.link(previous_observation_id, observation.id, "succession")
            links += 1
        previous_observation_id = observation.id

        for entity in _parse_instance_block(caption):
            entity_node = store.write_observation(
                text=" | ".join(
                    bit
                    for bit in (
                        f"entity {entity['type']}",
                        entity["label"],
                        entity["text"],
                        " ".join(f"{key}={value}" for key, value in entity["attrs"].items()),
                    )
                    if bit
                ),
                t_ms=observation.t_ms,
                source=f"{source_prefix}.entity",
                place=place,
                pose=pose,
                provenance={"moment_id": moment_id, "frame": row.get("frame")},
                metadata=entity,
                node_type="entity",
            )
            entity_nodes.append(entity_node.id)
            store.link(entity_node.id, observation.id, "same_entity")
            links += 1

    return KfIngestResult(
        observation_nodes=tuple(observation_nodes),
        entity_nodes=tuple(entity_nodes),
        link_count=links,
    )
