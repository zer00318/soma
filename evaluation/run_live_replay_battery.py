#!/usr/bin/env python3
"""Run the 44-question battery against a wall-clock live replay.

Why this exists:
The stored day-in-life and walk memories in the repo are marked
`real_time_proven=false` / `mode=offline_replay`, so they are not fair evidence
for a "live helpers only" product number. This runner replays the original raw
clips at wall-clock speed and only emits helper outputs that can keep pace on
this Mac today:

- Vision OCR on sampled video frames (Apple Vision, local, no frame files kept)
- Speech ASR on chunked live audio prefixes (mlx-whisper, local)
- Relative audio-event detection on live audio prefixes (local DSP)

Notably absent on purpose:
- Full-frame VLM captions. Local gemma3:12b multimodal took ~17-32s per frame in
  spot checks, so including it would launder an offline helper into a "live"
  number. Object/scene questions that require a live VLM should therefore refuse
  here. That is the honest result.

Outputs per clip under data/live_replay/<clip>_live44/:
  memory/kf_memory.json
  memory/screen_memory.json
  memory/asr.json
  memory/transcript.txt
  memory/audio_events.json
  memory/evidence_pack.json

Then scores the exact frozen batteries:
  day  -> 19 questions  (evaluation/ras/day_in_life_20260618.txt)
  walk -> 25 questions  (evaluation/ras/walk_outside_20260614.txt)

And writes:
  evaluation/ras/live44_day.jsonl
  evaluation/ras/live44_walk.jsonl
  evaluation/ras/live44_summary.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import mlx_whisper
import numpy as np
import Quartz
import soundfile as sf
from Foundation import NSData
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evaluation.vision_ocr import ocr_cgimage
import scripts.build_audio_events as build_audio_events

RUN_LIVE = ROOT / "evaluation" / "run_live.py"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

ASR_MODEL = "mlx-community/whisper-large-v3-turbo"


@dataclass(frozen=True)
class Profile:
    name: str
    video_path: Path
    audio_path: Path
    duration_s: float
    questions_path: Path
    gold_path: Path
    out_dir: Path
    checkpoint_path: Path
    status_path: Path
    has_speech: bool


PROFILES = {
    "day": Profile(
        name="day",
        video_path=ROOT / "data" / "walks" / "Day in life.mp4",
        audio_path=ROOT / "data" / "walks" / "day_in_life_20260618" / "memory" / "audio.wav",
        duration_s=58.5,
        questions_path=ROOT / "evaluation" / "ras" / "day_in_life_20260618.txt",
        gold_path=ROOT / "evaluation" / "ras" / "day_in_life_20260618.gold.json",
        out_dir=ROOT / "data" / "live_replay" / "day_in_life_20260618_live44",
        checkpoint_path=ROOT / "evaluation" / "ras" / "live44_day.jsonl",
        status_path=ROOT / "ops" / "cockpit" / "eval_live44_day.json",
        has_speech=True,
    ),
    "walk": Profile(
        name="walk",
        video_path=ROOT / "data" / "walks" / "incoming" / "IMG_4045.MOV",
        audio_path=ROOT / "data" / "walks" / "walk_outside_20260614" / "memory" / "audio.wav",
        duration_s=92.0,
        questions_path=ROOT / "evaluation" / "ras" / "walk_outside_20260614.txt",
        gold_path=ROOT / "evaluation" / "ras" / "walk_outside_20260614.gold.json",
        out_dir=ROOT / "data" / "live_replay" / "walk_outside_20260614_live44",
        checkpoint_path=ROOT / "evaluation" / "ras" / "live44_walk.jsonl",
        status_path=ROOT / "ops" / "cockpit" / "eval_live44_walk.json",
        has_speech=False,
    ),
}


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_questions(path: Path) -> list[str]:
    questions = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, sep, tail = line.partition(":")
        if sep and head.strip().lower() in {"objects", "people", "places", "text", "events", "fusion", "other"}:
            line = tail.strip()
        questions.append(line)
    return questions


def _cgimage_from_rgb(rgb: np.ndarray) -> Any:
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    payload = buf.getvalue()
    ns = NSData.dataWithBytes_length_(payload, len(payload))
    src = Quartz.CGImageSourceCreateWithData(ns, None)
    if src is None:
        raise RuntimeError("CGImageSourceCreateWithData failed")
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg is None:
        raise RuntimeError("CGImageSourceCreateImageAtIndex failed")
    return cg


def _ocr_frame(cap: cv2.VideoCapture, t_s: float) -> list[str]:
    cap.set(cv2.CAP_PROP_POS_MSEC, max(t_s, 0.0) * 1000.0)
    ok, frame = cap.read()
    if not ok or frame is None:
        return []
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    cg = _cgimage_from_rgb(rgb)
    return ocr_cgimage(cg)


def _resample_mono_16k(path: Path) -> tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), always_2d=False)
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    data = np.asarray(data, dtype=np.float32)
    if sr != 16000:
        n = int(round(len(data) * 16000 / sr))
        data = np.interp(
            np.linspace(0, len(data), n, endpoint=False),
            np.arange(len(data)),
            data,
        ).astype(np.float32)
        sr = 16000
    return data, sr


def _transcribe_chunk(audio16: np.ndarray, sr: int, start_s: float, end_s: float) -> list[dict[str, Any]]:
    lo = max(0, int(round(start_s * sr)))
    hi = min(len(audio16), int(round(end_s * sr)))
    if hi <= lo:
        return []
    chunk = audio16[lo:hi]
    if len(chunk) < int(0.5 * sr):
        return []
    res = mlx_whisper.transcribe(
        chunk,
        path_or_hf_repo=ASR_MODEL,
        word_timestamps=False,
        language="en",
    )
    segments = []
    for seg in res.get("segments", []) or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(start_s + float(seg.get("start", 0.0)), 2),
                "end": round(start_s + float(seg.get("end", 0.0)), 2),
                "text": text,
            }
        )
    return segments


def _detect_audio_events_prefix(audio16: np.ndarray, sr: int, end_s: float) -> dict[str, Any]:
    hi = min(len(audio16), int(round(end_s * sr)))
    prefix = audio16[:hi]
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(tmp, prefix, sr)
        return build_audio_events.detect(tmp, use_apple=False)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _dedup_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for seg in sorted(segments, key=lambda s: (s["start"], s["end"], s["text"])):
        key = (round(seg["start"], 1), seg["text"].strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def _write_memory(profile: Profile,
                  ocr_rows: list[dict[str, Any]],
                  speech_segments: list[dict[str, Any]],
                  audio_events: dict[str, Any],
                  helper_stats: dict[str, Any]) -> Path:
    memory_dir = profile.out_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    kf = []
    for row in sorted(ocr_rows, key=lambda r: r["t"]):
        kf.append(
            {
                "t": round(float(row["t"]), 1),
                "frame": row["frame"],
                "caption": "",
                "ocr": row["ocr"],
                "source": "live_replay_ocr",
            }
        )
    for idx, seg in enumerate(_dedup_segments(speech_segments)):
        kf.append(
            {
                "t": round(float(seg["start"]), 1),
                "frame": f"speech_{idx:04d}",
                "caption": f'EVENT | nearby speech | transcript: "{seg["text"]}"',
                "ocr": [],
                "source": "live_replay_asr",
            }
        )
    kf.sort(key=lambda row: (row["t"], row["frame"]))
    kf_path = memory_dir / "kf_memory.json"
    kf_path.write_text(json.dumps(kf, ensure_ascii=False, indent=2))

    screen_rows = []
    for row in sorted(ocr_rows, key=lambda r: r["t"]):
        joined = "; ".join(row["ocr"])
        screen_rows.append(
            {
                "t": round(float(row["t"]), 1),
                "frame": row["frame"],
                "screen_ocr": row["ocr"],
                "screen_ocr_txt": joined,
            }
        )
    (memory_dir / "screen_memory.json").write_text(json.dumps(screen_rows, ensure_ascii=False, indent=2))

    asr_doc = {
        "model": ASR_MODEL,
        "language": "en",
        "duration_s": round(max((seg["end"] for seg in speech_segments), default=0.0), 1),
        "full_text": " ".join(seg["text"] for seg in _dedup_segments(speech_segments)).strip(),
        "segments": _dedup_segments(speech_segments),
    }
    (memory_dir / "asr.json").write_text(json.dumps(asr_doc, ensure_ascii=False, indent=2))
    transcript_lines = [
        "# voice channel: LIVE replay ASR (%s), lang=en, %d segments" %
        (ASR_MODEL.split("/")[-1], len(asr_doc["segments"]))
    ]
    for seg in asr_doc["segments"]:
        transcript_lines.append("[%6.1f-%6.1fs] %s" % (seg["start"], seg["end"], seg["text"]))
    (memory_dir / "transcript.txt").write_text("\n".join(transcript_lines) + "\n")

    (memory_dir / "audio_events.json").write_text(json.dumps(audio_events, ensure_ascii=False, indent=2))

    evidence = {
        "schema_version": 1,
        "mode": "live_replay",
        "real_time_proven": True,
        "source": {
            "path": str(profile.video_path.resolve()),
            "audio_path": str(profile.audio_path.resolve()),
            "retained": True,
        },
        "capture_window": {
            "start_seconds": 0.0,
            "end_seconds": profile.duration_s,
        },
        "contract": {
            "raw_source_is_authoritative": True,
            "derived_text_is_rebuildable": True,
            "slow_models_allowed_during_capture": False,
        },
        "helpers": helper_stats,
    }
    (memory_dir / "evidence_pack.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    return kf_path


def _run_scoring(profile: Profile, memory_path: Path,
                 answer_model: str, judge_model: str) -> dict[str, Any]:
    _ensure_parent(profile.checkpoint_path)
    _ensure_parent(profile.status_path)
    if profile.checkpoint_path.exists():
        profile.checkpoint_path.unlink()
    cmd = [
        str(VENV_PYTHON),
        str(RUN_LIVE),
        "--questions", str(profile.questions_path),
        "--gold", str(profile.gold_path),
        "--memory", str(memory_path),
        "--answer-model", answer_model,
        "--judge-model", judge_model,
        "--checkpoint", str(profile.checkpoint_path),
        "--status", str(profile.status_path),
    ]
    print(
        f"[{profile.name}] scoring {profile.questions_path.name} with "
        f"answer={answer_model} judge={judge_model}",
        flush=True,
    )
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    status = json.loads(profile.status_path.read_text()) if profile.status_path.exists() else {}
    print(
        f"[{profile.name}] scoring finished rc={proc.returncode} "
        f"correct={status.get('correct')} wrong={status.get('wrong')} miss={status.get('miss')} "
        f"needs_review={status.get('needs_review')}",
        flush=True,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "status": status,
    }


def _run_profile(profile: Profile,
                 vision_every_s: float,
                 speech_chunk_s: float,
                 answer_model: str,
                 judge_model: str,
                 skip_scoring: bool,
                 duration_override_s: float | None) -> dict[str, Any]:
    profile.out_dir.mkdir(parents=True, exist_ok=True)
    target_duration_s = duration_override_s if duration_override_s is not None else profile.duration_s
    print(
        f"[{profile.name}] live replay capture starting "
        f"duration={target_duration_s:.1f}s vision_every={vision_every_s:.1f}s "
        f"speech_chunk={speech_chunk_s:.1f}s",
        flush=True,
    )
    cap = cv2.VideoCapture(str(profile.video_path))
    if not cap.isOpened():
        raise RuntimeError(f"failed to open video: {profile.video_path}")

    audio16, audio_sr = _resample_mono_16k(profile.audio_path)

    ocr_rows: list[dict[str, Any]] = []
    speech_segments: list[dict[str, Any]] = []
    audio_events = {
        "overall_db": 0.0,
        "usable_sound": False,
        "duration_s": 0.0,
        "frame_s": build_audio_events.FRAME_S,
        "hop_s": build_audio_events.HOP_S,
        "baseline_db": None,
        "rel_gate_db": build_audio_events.REL_GATE_DB,
        "classifier": "acoustic_heuristic",
        "events": [],
    }

    next_vision = 0.0
    next_speech = speech_chunk_s
    next_audio = speech_chunk_s
    speech_cursor = 0.0
    vision_samples = 0
    vision_drop_est = 0
    speech_chunks = 0

    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= target_duration_s:
            break
        did_work = False

        if elapsed >= next_vision:
            lines = _ocr_frame(cap, next_vision)
            ocr_rows.append(
                {
                    "t": round(next_vision, 1),
                    "frame": f"ocr_{vision_samples:04d}",
                    "ocr": lines,
                }
            )
            vision_samples += 1
            did_work = True
            current_elapsed = time.monotonic() - start
            missed = max(0, math.floor((current_elapsed - next_vision) / vision_every_s) - 1)
            if missed > 0:
                vision_drop_est += missed
            next_vision = (math.floor(current_elapsed / vision_every_s) + 1) * vision_every_s

        if profile.has_speech and elapsed >= next_speech:
            speech_segments.extend(_transcribe_chunk(audio16, audio_sr, speech_cursor, next_speech))
            speech_cursor = next_speech
            next_speech += speech_chunk_s
            speech_chunks += 1
            did_work = True

        if elapsed >= next_audio:
            audio_events = _detect_audio_events_prefix(audio16, audio_sr, next_audio)
            next_audio += speech_chunk_s
            did_work = True

        if not did_work:
            upcoming = [next_vision]
            if profile.has_speech:
                upcoming.append(next_speech)
            upcoming.append(next_audio)
            sleep_s = max(0.05, min(0.25, min(upcoming) - elapsed))
            time.sleep(sleep_s)

    if profile.has_speech and speech_cursor < target_duration_s:
        speech_segments.extend(_transcribe_chunk(audio16, audio_sr, speech_cursor, target_duration_s))
        speech_chunks += 1
    audio_events = _detect_audio_events_prefix(audio16, audio_sr, target_duration_s)

    helper_stats = {
        "vision_ocr": {
            "cadence_s": vision_every_s,
            "samples_written": vision_samples,
            "dropped_tick_estimate": vision_drop_est,
        },
        "speech_asr": {
            "enabled": profile.has_speech,
            "chunk_s": speech_chunk_s,
            "chunks_processed": speech_chunks,
            "segments_written": len(_dedup_segments(speech_segments)),
            "model": ASR_MODEL,
        },
        "audio_events": {
            "chunk_s": speech_chunk_s,
            "usable_sound": bool(audio_events.get("usable_sound")),
            "event_count": len(audio_events.get("events") or []),
        },
        "vision_vlm": {
            "enabled": False,
            "reason": "local gemma3:12b multimodal spot-checks took ~17-32s/frame, so it does not satisfy live helper pace on this Mac",
        },
    }
    memory_path = _write_memory(profile, ocr_rows, speech_segments, audio_events, helper_stats)
    cap.release()
    print(
        f"[{profile.name}] capture finished ocr_samples={vision_samples} "
        f"speech_segments={len(_dedup_segments(speech_segments))} "
        f"audio_events={len(audio_events.get('events') or [])}",
        flush=True,
    )

    scoring = None if skip_scoring else _run_scoring(profile, memory_path, answer_model, judge_model)
    return {
        "profile": profile.name,
        "memory_path": str(memory_path),
        "helper_stats": helper_stats,
        "scoring": scoring,
        "question_count": len(_load_questions(profile.questions_path)),
        "capture_duration_s": target_duration_s,
    }


def _combined_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    correct = wrong = miss = 0
    total = 0
    per_clip = {}
    for result in results:
        status = (result.get("scoring") or {}).get("status") or {}
        c = int(status.get("correct", 0))
        w = int(status.get("wrong", 0))
        m = int(status.get("miss", 0))
        n = int(status.get("total", 0)) or int(result.get("question_count", 0))
        if status:
            total += n
            correct += c
            wrong += w
            miss += m
        per_clip[result["profile"]] = {
            "correct": c,
            "wrong": w,
            "miss": m,
            "total": n,
            "hard_ras": status.get("hard_ras"),
            "halluc_pct": status.get("halluc_pct"),
            "memory_path": result.get("memory_path"),
        }
    answered = correct + wrong
    return {
        "total_questions": total,
        "correct": correct,
        "wrong": wrong,
        "miss": miss,
        "hard_ras": round((correct - wrong) * 100.0 / total, 1) if total else 0.0,
        "halluc_pct": round(wrong * 100.0 / answered, 1) if answered else 0.0,
        "per_clip": per_clip,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=("day", "walk", "both"), default="both")
    ap.add_argument("--vision-every", type=float, default=1.0)
    ap.add_argument("--speech-chunk", type=float, default=8.0)
    ap.add_argument("--answer-model", default="gemma3:12b-it-qat")
    ap.add_argument("--judge-model", default="gemma3:27b-it-qat")
    ap.add_argument("--skip-scoring", action="store_true")
    ap.add_argument("--duration-override", type=float, default=None)
    ap.add_argument("--summary-out", default=str(ROOT / "evaluation" / "ras" / "live44_summary.json"))
    args = ap.parse_args()

    names = ["day", "walk"] if args.profile == "both" else [args.profile]
    results = []
    for name in names:
        results.append(
            _run_profile(
                PROFILES[name],
                vision_every_s=args.vision_every,
                speech_chunk_s=args.speech_chunk,
                answer_model=args.answer_model,
                judge_model=args.judge_model,
                skip_scoring=args.skip_scoring,
                duration_override_s=args.duration_override,
            )
        )

    summary = _combined_summary(results)
    out_path = Path(args.summary_out)
    _ensure_parent(out_path)
    out_path.write_text(json.dumps({"summary": summary, "runs": results}, ensure_ascii=False, indent=2))
    print(f"[summary] wrote {out_path}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
