#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _frame_time_ms(path: Path, fallback_index: int) -> int:
    try:
        return int(round(float(path.stem) * 1000))
    except ValueError:
        return fallback_index * 1000


def _choose_frames(frame_paths: list[Path], count: int) -> list[Path]:
    if len(frame_paths) <= count:
        return frame_paths
    chosen: list[Path] = []
    for index in range(count):
        source_index = round(index * (len(frame_paths) - 1) / max(1, count - 1))
        chosen.append(frame_paths[source_index])
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in chosen:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _refresh_selected_frames(selected: list[Path], out_dir: Path) -> None:
    selected_dir = out_dir / "selected_frames"
    selected_dir.mkdir(parents=True, exist_ok=True)
    for existing in selected_dir.iterdir():
        existing.unlink()
    for frame_path in selected:
        for source in (
            frame_path,
            frame_path.with_suffix(".pose.json"),
            frame_path.with_suffix(".depth.json"),
        ):
            if not source.exists():
                continue
            target = selected_dir / source.name
            target.symlink_to(source.resolve())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-dir", default="data/phone_captures/bedroom_kf40")
    parser.add_argument("--out-dir", default="ops/fixtures/world_grounded")
    parser.add_argument("--count", type=int, default=6)
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    out_dir = Path(args.out_dir)
    frame_paths = sorted(frames_dir.glob("*.jpg"), key=lambda path: float(path.stem))
    selected = _choose_frames(frame_paths, max(1, args.count))

    manifest = {
        "session_id": frames_dir.name,
        "source_frames_dir": str(frames_dir.resolve()),
        "selected_frame_count": len(selected),
        "frames": [
            {
                "frame_id": frame_path.name,
                "frame_path": str(frame_path.resolve()),
                "pose_path": str(frame_path.with_suffix(".pose.json").resolve()),
                "depth_path": str(frame_path.with_suffix(".depth.json").resolve()),
                "t_ms": _frame_time_ms(frame_path, index),
            }
            for index, frame_path in enumerate(selected)
        ],
        "helper_jobs": [
            {
                "helper_type": helper_type,
                "goal": goal,
            }
            for helper_type, goal in (
                ("vlm", "Describe the whole visible scene with concrete objects and visible text."),
                ("ocr", "Transcribe visible text only when it can actually be read."),
                ("colour", "Call out object and clothing colours only when grounded."),
                ("texture", "Call out object and clothing textures only when grounded."),
            )
        ],
    }

    binder_seed = {
        "session_id": "binder-fixture-bedroom",
        "coordinate_frame": {"session_id": "binder-fixture-bedroom", "origin_id": "arkit_session_origin"},
        "observations": [
            {
                "id": "obs-colour-a",
                "text": "person A shirt colour is green",
                "helper_type": "colour",
                "t_ms": 1000,
                "spatial_anchor": {"kind": "world_point", "coordinates": {"xyz": [0.0, 0.0, 0.0]}, "bounds": {"radius_m": 0.25}},
                "metadata": {"subject_hint": "person A", "attribute_kind": "color", "attribute_value": "green"},
            },
            {
                "id": "obs-texture-a",
                "text": "person A shirt texture is ribbed",
                "helper_type": "texture",
                "t_ms": 1200,
                "spatial_anchor": {"kind": "world_point", "coordinates": {"xyz": [0.1, 0.0, 0.0]}, "bounds": {"radius_m": 0.25}},
                "metadata": {"subject_hint": "person A", "attribute_kind": "texture", "attribute_value": "ribbed"},
            },
            {
                "id": "obs-speech-a",
                "text": "person A transcript: hello there",
                "helper_type": "whisper",
                "t_ms": 1300,
                "spatial_anchor": {"kind": "audio_origin", "coordinates": {"xyz": [0.05, 0.0, 0.0]}, "bounds": {"radius_m": 0.5}},
                "metadata": {"subject_hint": "person A", "transcript": "hello there"},
            },
            {
                "id": "obs-colour-b",
                "text": "person B shirt colour is blue",
                "helper_type": "colour",
                "t_ms": 2000,
                "spatial_anchor": {"kind": "world_point", "coordinates": {"xyz": [3.0, 0.0, 0.0]}, "bounds": {"radius_m": 0.25}},
                "metadata": {"subject_hint": "person B", "attribute_kind": "color", "attribute_value": "blue"},
            },
            {
                "id": "obs-speech-b",
                "text": "person B transcript: see you soon",
                "helper_type": "whisper",
                "t_ms": 2100,
                "spatial_anchor": {"kind": "audio_origin", "coordinates": {"xyz": [3.1, 0.0, 0.0]}, "bounds": {"radius_m": 0.5}},
                "metadata": {"subject_hint": "person B", "transcript": "see you soon"},
            },
        ],
    }

    brain_seed = {
        "questions": [
            {
                "question": "What did the person with the green shirt say?",
                "expect_subject": "person A",
                "expect_words": ["hello", "there"],
            },
            {
                "question": "What colour was person B's shirt?",
                "expect_subject": "person B",
                "expect_words": ["blue"],
            },
        ]
    }

    _refresh_selected_frames(selected, out_dir)
    _write_json(out_dir / "recorded_frames_manifest.json", manifest)
    _write_json(out_dir / "sample_binder_inputs.json", binder_seed)
    _write_json(out_dir / "sample_brain_questions.json", brain_seed)
    print(f"wrote fixture manifest to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
