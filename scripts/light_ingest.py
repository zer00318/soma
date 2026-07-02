#!/usr/bin/env python3
"""Light demo ingest for recorded room keyframes.

This path keeps live ingestion cheap: one helper write per frame plus cheap candidate links.
If requested, it then runs the sleep binder as a second phase over the stored observations.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from trace_memory.store import (  # noqa: E402
    SleepConsolidator,
    TraceMemoryStore,
    observation_overlap_score,
    observation_time_range,
    scene_frustum_anchor,
    session_coordinate_frame,
)

HOST = "http://127.0.0.1:11434"
SCENE_PROMPT = (
    "Precise perception sensor. Report ONLY what is literally visible in this frame. "
    "(1) Each distinct physical object with colour/material/state (open/closed, on/off, "
    "a dial's number, count if several identical). (2) Transcribe ALL visible text VERBATIM "
    "- labels, screens, dials, battery %, app names. If unreadable write [unreadable]. No guessing."
)
RELATION_PROMPT = (
    "Precise relation sensor. Report ONLY directly visible spatial relations and state in this frame. "
    "Use short atomic bullets. Include: what is on/under/next to what, open/closed, on/off, dial value "
    "if readable, identical-object counts if visible together, and drinkable containers if present. "
    "Ignore document/article body text unless it is the app/window title or menu bar."
)
SCREEN_PROMPT = (
    "Precise screen-state sensor. If a screen is visible, report ONLY short atomic bullets for: "
    "the app/window title, menu bar or toolbar text, time/date, battery percentage, and clearly visible "
    "tabs/sidebar labels. Ignore long document/chat body text. If no readable screen state is visible, say None."
)
SCREEN_FRAME_CUES = (
    "laptop",
    "macbook",
    "screen",
    "display",
    "window help",
    "chat",
    "cowork",
    "code",
)
RELATION_SCREEN_NOISE_CUES = (
    "app window",
    "window title",
    "menu bar",
    "battery percentage",
    "time/date",
    "tabs/sidebar",
    "sidebar labels",
    "file named",
    "document:",
    "open in",
)

_HEADER_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_NUMBERED_RE = re.compile(r"^\d+\.\s+(?P<body>.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(?P<body>.+?)\s*$")
_DASH_SPLIT_RE = re.compile(r"\s+[—–-]\s+")
_CODE_RE = re.compile(r"`([^`]+)`")


def _frame_time_ms(path: Path, fallback_index: int) -> int:
    try:
        return int(round(float(path.stem) * 1000))
    except ValueError:
        return fallback_index * 1000


def _pose_degrees(pose: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pose:
        return None
    out = dict(pose)
    for key in ("yaw", "pitch", "roll"):
        value = pose.get(key)
        if isinstance(value, (int, float)):
            out[f"{key}_deg"] = round(float(value) * 180.0 / 3.141592653589793, 2)
    return out


def _load(path: Path) -> dict[str, Any] | None:
    if path.exists():
        return json.loads(path.read_text())
    return None


def _gen_local(image_b64: str, model: str, prompt: str, timeout: int = 180) -> str:
    body = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        f"{HOST}/api/generate",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout)).get("response", "").strip()


def _gen_frontier(image_b64: str, model: str, prompt: str, timeout: int = 90) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("no ANTHROPIC_API_KEY for frontier perception")
    body = {
        "model": model,
        "max_tokens": 700,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    resp = json.load(urllib.request.urlopen(req, timeout=timeout))
    return "".join(block.get("text", "") for block in resp.get("content", [])).strip()


def _gen(image_b64: str, model: str, backend: str, prompt: str, timeout: int = 180) -> str:
    if backend == "frontier":
        return _gen_frontier(
            image_b64,
            os.environ.get("TRACE_FRONTIER_MODEL", "claude-sonnet-4-6"),
            prompt,
        )
    return _gen_local(image_b64, model, prompt, timeout)


def _place_bucket(pose: dict[str, Any] | None) -> str | None:
    if not pose:
        return None
    yaw = pose.get("yaw_deg")
    pitch = pose.get("pitch_deg")
    if not isinstance(yaw, (int, float)) or not isinstance(pitch, (int, float)):
        return None
    return f"yaw:{int(round(float(yaw) / 15.0) * 15)}|pitch:{int(round(float(pitch) / 15.0) * 15)}"


def _clean_inline(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = cleaned.replace("•", "")
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" -:")


def _section_kind(title: str) -> str | None:
    lowered = title.lower()
    if "physical object" in lowered or "visible object" in lowered or lowered in {"bed", "suitcase", "window", "nightstand"}:
        return "physical_object"
    if "transcribed text" in lowered or "verbatim text" in lowered or "visible text" in lowered:
        return "screen_text"
    if "screen" in lowered or "menu bar" in lowered or "app" in lowered:
        return "screen_text"
    if "relation" in lowered or "state" in lowered or "count" in lowered:
        return "relation"
    return None


def _subject_hint(body: str) -> str | None:
    hint = _clean_inline(_DASH_SPLIT_RE.split(body, maxsplit=1)[0])
    if not hint:
        return None
    hint = hint.split(":", 1)[0].strip()
    if len(hint) > 80:
        return None
    return hint


def _helper_type_for_kind(kind: str, default_helper_type: str | None = None) -> str:
    if default_helper_type:
        return default_helper_type
    if kind == "physical_object":
        return "vlm_object"
    if kind == "relation":
        return "spatial_relation"
    return "ocr"


def _extract_helper_atoms(
    text: str,
    *,
    default_kind: str | None = None,
    default_helper_type: str | None = None,
    default_title: str = "",
) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    current_title = default_title
    current_kind: str | None = default_kind
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped == "---":
            continue
        header = _HEADER_RE.match(stripped)
        if header:
            current_title = _clean_inline(header.group("title"))
            current_kind = _section_kind(current_title) or default_kind
            continue
        if current_kind is None:
            continue

        body: str | None = None
        numbered = _NUMBERED_RE.match(stripped)
        bullet = _BULLET_RE.match(stripped)
        if numbered:
            body = numbered.group("body")
        elif bullet:
            body = bullet.group("body")
        elif current_kind == "screen_text":
            code_fragments = _CODE_RE.findall(stripped)
            if code_fragments:
                body = " | ".join(_clean_inline(fragment) for fragment in code_fragments if _clean_inline(fragment))
            elif stripped.startswith((">", '"', "'")):
                body = stripped.lstrip("> ").strip()
        if not body:
            continue

        cleaned = _clean_inline(body)
        if not cleaned or cleaned.lower() == "none":
            continue
        if current_kind == "relation":
            lowered = cleaned.lower()
            if any(cue in lowered for cue in RELATION_SCREEN_NOISE_CUES):
                continue
        atom: dict[str, Any] = {
            "section_kind": current_kind,
            "section_title": current_title,
            "text": cleaned,
        }
        atom["helper_type"] = _helper_type_for_kind(current_kind, default_helper_type)
        atom["subject_hint"] = _subject_hint(cleaned) if current_kind in {"physical_object", "relation"} else None
        atoms.append(atom)
    return atoms


def _extract_frame_atoms(text: str) -> list[dict[str, Any]]:
    return _extract_helper_atoms(text)


def _canonicalize_helper_text(helper_prompt: str, atoms: list[dict[str, Any]], fallback_text: str) -> str:
    if not atoms:
        return fallback_text
    if helper_prompt == "spatial_relations":
        header = "## Spatial Relations"
    elif helper_prompt == "screen_state":
        header = "## Screen State"
    else:
        return fallback_text
    lines = [header]
    for atom in atoms:
        lines.append(f"- {atom['text']}")
    return "\n".join(lines)


def _screen_visible(text: str) -> bool:
    lowered = text.lower()
    return any(cue in lowered for cue in SCREEN_FRAME_CUES)


def _write_helper_observation(
    *,
    store: TraceMemoryStore,
    frame_path: Path,
    index: int,
    t_ms: int,
    coordinate_frame: Any,
    pose: dict[str, Any] | None,
    place: str | None,
    backend: str,
    frames_dir: Path,
    helper_prompt: str,
    parent_helper_type: str,
    text: str,
    default_kind: str | None = None,
    default_detail_helper_type: str | None = None,
    skip_if_empty_atoms: bool = False,
) -> tuple[Any | None, int]:
    atoms = _extract_helper_atoms(
        text,
        default_kind=default_kind,
        default_helper_type=default_detail_helper_type,
        default_title=helper_prompt,
    )
    if skip_if_empty_atoms and not atoms:
        return None, 0
    canonical_text = _canonicalize_helper_text(helper_prompt, atoms, text)

    node = store.write_canonical_observation(
        text=canonical_text,
        t_ms=t_ms,
        source="phone_camera",
        helper_type=parent_helper_type,
        coordinate_frame=coordinate_frame,
        time_range=observation_time_range(t_ms),
        spatial_anchor=scene_frustum_anchor(
            pose=pose,
            metadata={"frame_ids": [frame_path.name], "ingest_backend": backend},
        ),
        provenance={
            "frame": frame_path.name,
            "light_ingest": True,
            "backend": backend,
            "frames_dir": str(frames_dir),
        },
        source_support={"frame_ids": [frame_path.name], "frame_paths": [str(frame_path)]},
        place=place,
        pose=pose,
        metadata={"frame_index": index, "helper_prompt": helper_prompt},
        immutable_raw=True,
    )
    detail_written = 0
    for atom_index, atom in enumerate(atoms):
        detail_node = store.write_canonical_observation(
            text=atom["text"],
            t_ms=t_ms,
            source="phone_camera",
            helper_type=str(atom["helper_type"]),
            coordinate_frame=coordinate_frame,
            time_range=observation_time_range(t_ms),
            spatial_anchor=scene_frustum_anchor(
                pose=pose,
                metadata={"frame_ids": [frame_path.name], "ingest_backend": backend},
            ),
            provenance={
                "frame": frame_path.name,
                "light_ingest": True,
                "backend": backend,
                "frames_dir": str(frames_dir),
                "parent_frame_node": node.id,
            },
            source_support={"frame_ids": [frame_path.name], "frame_paths": [str(frame_path)]},
            place=place,
            pose=pose,
            metadata={
                "frame_index": index,
                "parent_frame_node": node.id,
                "section_kind": atom["section_kind"],
                "section_title": atom["section_title"],
                "subject_hint": atom["subject_hint"],
                "helper_prompt": helper_prompt,
            },
            immutable_raw=True,
        )
        store.link(
            node.id,
            detail_node.id,
            "scene_detail",
            metadata={
                "builder": "light_ingest",
                "section_kind": atom["section_kind"],
                "atom_index": atom_index,
                "helper_prompt": helper_prompt,
            },
        )
        detail_written += 1
    return node, detail_written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--store", required=True)
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--backend", choices=("local", "frontier"), default="local")
    ap.add_argument("--helper-mode", choices=("scene_only", "multi_helper"), default="scene_only")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--sleep-bind", action="store_true")
    args = ap.parse_args()

    store_path = Path(args.store)
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(store_path) + suffix)
            if candidate.exists():
                candidate.unlink()

    frames_dir = Path(args.frames_dir)
    frames = sorted(frames_dir.glob("*.jpg"), key=lambda path: float(path.stem))
    coordinate_frame = session_coordinate_frame(frames_dir.name)
    store = TraceMemoryStore(str(store_path))
    written = 0
    helper_written = 0
    detail_written = 0
    recent_nodes: deque[Any] = deque(maxlen=3)
    try:
        for index, frame_path in enumerate(frames):
            image_b64 = base64.b64encode(frame_path.read_bytes()).decode()
            t0 = time.time()
            try:
                text = _gen(image_b64, args.model, args.backend, SCENE_PROMPT)
            except Exception as exc:  # noqa: BLE001
                print(f"  frame {index} FAILED {exc}", flush=True)
                continue
            if not text:
                continue

            pose = _pose_degrees(_load(frame_path.with_suffix(".pose.json")))
            t_ms = _frame_time_ms(frame_path, index)
            place = _place_bucket(pose)
            node, scene_details = _write_helper_observation(
                store=store,
                frame_path=frame_path,
                index=index,
                t_ms=t_ms,
                coordinate_frame=coordinate_frame,
                pose=pose,
                place=place,
                backend=args.backend,
                frames_dir=frames_dir,
                helper_prompt="scene_perception",
                parent_helper_type="vlm",
                text=text,
            )
            if node is None:
                continue
            detail_written += scene_details

            if args.helper_mode == "multi_helper":
                try:
                    relation_text = _gen(image_b64, args.model, args.backend, RELATION_PROMPT)
                except Exception as exc:  # noqa: BLE001
                    print(f"  frame {index} relation FAILED {exc}", flush=True)
                    relation_text = ""
                if relation_text:
                    relation_node, relation_details = _write_helper_observation(
                        store=store,
                        frame_path=frame_path,
                        index=index,
                        t_ms=t_ms,
                        coordinate_frame=coordinate_frame,
                        pose=pose,
                        place=place,
                        backend=args.backend,
                        frames_dir=frames_dir,
                        helper_prompt="spatial_relations",
                        parent_helper_type="relation_helper",
                        text=relation_text,
                        default_kind="relation",
                        default_detail_helper_type="spatial_relation",
                        skip_if_empty_atoms=True,
                    )
                    if relation_node is not None:
                        store.link(
                            relation_node.id,
                            node.id,
                            "same_frame_helper",
                            metadata={"builder": "light_ingest", "helper_prompt": "spatial_relations"},
                        )
                        store.link(
                            node.id,
                            relation_node.id,
                            "same_frame_helper",
                            metadata={"builder": "light_ingest", "helper_prompt": "spatial_relations"},
                        )
                        helper_written += 1
                        detail_written += relation_details

                if _screen_visible(text):
                    try:
                        screen_text = _gen(image_b64, args.model, args.backend, SCREEN_PROMPT)
                    except Exception as exc:  # noqa: BLE001
                        print(f"  frame {index} screen FAILED {exc}", flush=True)
                        screen_text = ""
                    if screen_text:
                        screen_node, screen_details = _write_helper_observation(
                            store=store,
                            frame_path=frame_path,
                            index=index,
                            t_ms=t_ms,
                            coordinate_frame=coordinate_frame,
                            pose=pose,
                            place=place,
                            backend=args.backend,
                            frames_dir=frames_dir,
                            helper_prompt="screen_state",
                            parent_helper_type="screen_helper",
                            text=screen_text,
                            default_kind="screen_text",
                            default_detail_helper_type="screen_state",
                            skip_if_empty_atoms=True,
                        )
                        if screen_node is not None:
                            store.link(
                                screen_node.id,
                                node.id,
                                "same_frame_helper",
                                metadata={"builder": "light_ingest", "helper_prompt": "screen_state"},
                            )
                            store.link(
                                node.id,
                                screen_node.id,
                                "same_frame_helper",
                                metadata={"builder": "light_ingest", "helper_prompt": "screen_state"},
                            )
                            helper_written += 1
                            detail_written += screen_details

            if recent_nodes:
                previous = recent_nodes[-1]
                store.link(
                    previous.id,
                    node.id,
                    "succession",
                    metadata={"builder": "light_ingest"},
                )
                for candidate in recent_nodes:
                    overlap = observation_overlap_score(candidate, node)
                    if overlap < 0.35:
                        continue
                    store.link(
                        candidate.id,
                        node.id,
                        "candidate_same_context",
                        weight=overlap,
                        metadata={"builder": "light_ingest", "space_time_score": overlap},
                    )

            recent_nodes.append(node)
            written += 1
            preview = text[:80].replace("\n", " ")
            print(f"  [{written}/{len(frames)}] {time.time()-t0:.1f}s :: {preview}", flush=True)

        if args.sleep_bind:
            summary = SleepConsolidator(store).consolidate()
            print(
                f"SLEEP_BIND: grouped={summary.grouped_observation_count} "
                f"composed={summary.composed_memory_count} links={summary.link_count}",
                flush=True,
            )
        print(
            f"DONE: {written} scene nodes, {helper_written} helper nodes, {detail_written} detail nodes",
            flush=True,
        )
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
