#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path):
    return json.loads(path.read_text())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


_AUTHORED_NODE_TYPES = {"entity_memory", "event_memory", "group_memory", "composed_memory", "abstraction"}
_RELATION_SCREEN_NOISE_CUES = (
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


def _contains_words(text: str, words: list[str]) -> bool:
    lowered = str(text).lower()
    return all(str(word).lower() in lowered for word in words)


def validate_manifest(root: Path) -> None:
    manifest = _load(root / "recorded_frames_manifest.json")
    frames = manifest.get("frames") or []
    _require(frames, "manifest has no frames")
    for row in frames:
        _require(Path(row["frame_path"]).exists(), f"missing frame {row['frame_path']}")


def validate_helper(root: Path) -> None:
    rows = _load(root / "helper_outputs.json")
    _require(isinstance(rows, list) and rows, "helper outputs missing or empty")
    helper_types: set[str] = set()
    for row in rows:
        _require(row.get("node_type") == "observation", "helper outputs must contain raw observations only")
        _require(row.get("text"), "helper output missing text")
        _require(row.get("helper_type"), "helper output missing helper_type")
        _require(row.get("coordinate_frame"), "helper output missing coordinate_frame")
        _require(row.get("spatial_anchor"), "helper output missing spatial_anchor")
        _require(row.get("time_range"), "helper output missing time_range")
        _require(row.get("derived") is False, "helper output must not be derived")
        _require(row.get("immutable_raw") is True, "helper output must be immutable raw evidence")
        if str(row.get("helper_type") or "") in {"spatial_relation", "relation_helper"}:
            lowered = str(row.get("text") or "").lower()
            _require(
                not any(cue in lowered for cue in _RELATION_SCREEN_NOISE_CUES),
                "relation helper output contains screen-state noise",
            )
        helper_types.add(str(row.get("helper_type")))
    _require(len(helper_types) >= 2, "helper outputs must exercise multiple helper types")


def validate_binder(root: Path) -> None:
    payload = _load(root / "binder_outputs.json")
    memories = payload.get("memories") or []
    _require(memories, "binder outputs missing memories")
    for memory in memories:
        _require(memory.get("node_type") in _AUTHORED_NODE_TYPES, "binder outputs must be authored memories")
        _require(memory.get("text"), "binder memory missing text")
        _require(memory.get("support_ids"), "binder memory missing support_ids")


def validate_brain(root: Path) -> None:
    rows = _load(root / "brain_outputs.json")
    _require(isinstance(rows, list) and rows, "brain outputs missing or empty")
    for row in rows:
        _require("question" in row and "answer" in row, "brain output missing question/answer")
        _require(isinstance(row.get("evidence_chain"), list), "brain output missing evidence_chain")
        _require(row["evidence_chain"], "brain output missing retrieved evidence")
        expect_subject = str(row.get("expect_subject") or "").strip()
        expect_words = [str(word) for word in (row.get("expect_words") or []) if str(word).strip()]
        if expect_subject:
            _require(
                any(expect_subject.lower() in str(item.get("text") or "").lower() for item in row["evidence_chain"]),
                f"brain evidence missing expected subject {expect_subject!r}",
            )
        if expect_words:
            combined = " ".join(str(item.get("text") or "") for item in row["evidence_chain"])
            _require(
                _contains_words(combined, expect_words),
                f"brain evidence missing expected words {expect_words!r}",
            )
        authored_rows = [
            item for item in row["evidence_chain"]
            if str(item.get("type") or "") in _AUTHORED_NODE_TYPES
        ]
        if authored_rows:
            _require(
                any(item.get("citation_ids") for item in authored_rows),
                "authored brain evidence must cite raw support",
            )
        if str(row.get("reasoner") or "") != "heuristic" and expect_words:
            answer = str(row.get("answer") or "")
            _require(
                (not bool(row.get("refused"))) and _contains_words(answer, expect_words),
                "non-heuristic brain output must answer from the expected supported words",
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="ops/fixtures/world_grounded")
    parser.add_argument("--stage", choices=("manifest", "helper", "binder", "brain", "all"), default="all")
    args = parser.parse_args()
    root = Path(args.root)

    if args.stage in {"manifest", "all"}:
        validate_manifest(root)
    if args.stage in {"helper", "all"}:
        validate_helper(root)
    if args.stage in {"binder", "all"}:
        validate_binder(root)
    if args.stage in {"brain", "all"}:
        validate_brain(root)
    print(f"validated {args.stage} fixtures under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
