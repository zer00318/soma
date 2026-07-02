#!/usr/bin/env python3
"""Day-in-life PERCEPTION harness (offline, one-time) — the reproducible replacement for the
prior session's scratchpad pipeline. Turns `data/phone_captures/Day in the life.mp4` into a
committed TRACE store the demo/scorer reads.

Three real perception channels, exactly the on-device society (run here on the Mac for the
one-time build; live they run on the phone):
  - Apple Vision OCR (pyobjc)      → screen text, signs, clocks, logos   (helper=ocr)
  - gemma3 vision (ollama)         → scene/object/self captions          (helper=vlm_object)
  - Whisper ASR (dense windows)    → speech: names, greetings            (helper=asr)

Every record is written through the REAL scripts.trace_hub.Hub.ingest seam (source=phone_camera,
helper-tagged, real timestamps) — the same path the live phone uses — so the store is identical
in shape to a live capture. Raw frames are held in memory and never persisted (privacy invariant).

    .venv/bin/python scripts/day_in_life/perceive.py \
        [--video data/phone_captures/"Day in the life.mp4"] \
        [--store evaluation/day_in_life/day_in_life.sqlite3] \
        [--fps 1.5] [--vlm-model gemma3:12b-it-qat] [--max-vlm 48] [--resume]

Resumable: skips frames already perceived (keyed by frame index in the store), so a long VLM
pass can be re-run after an interruption. Runtime ~20-40 min for the VLM pass (see the memory
note: gemma3:12b vision ≈ 22s/frame); OCR+ASR are minutes.
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.trace_hub import Hub  # noqa: E402

HOST = "http://127.0.0.1:11434"
# Anchor time: the founder's gold is keyed to the clip only by ORDER, so any monotonic base
# works. Fixed (not now()) for reproducibility. 2026-06-18 10:00:00Z, +100ms per event.
BASE_MS = 1_781_774_400_000


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---- Apple Vision OCR (in-memory, native) -------------------------------------------------

def _ocr_bgr(bgr: np.ndarray, *, min_conf: float = 0.3) -> list[str]:
    """Verbatim text lines from an image via Apple Vision (accurate, language-corrected)."""
    import Quartz
    import Vision
    from Foundation import NSData

    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        return []
    data = NSData.dataWithBytes_length_(buf.tobytes(), len(buf))
    src = Quartz.CGImageSourceCreateWithData(data, None)
    if src is None:
        return []
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if cg is None:
        return []
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(1)  # accurate
    req.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    handler.performRequests_error_([req], None)
    lines: list[str] = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if cand and cand[0].confidence() >= min_conf:
            txt = str(cand[0].string()).strip()
            if len(txt) >= 2:
                lines.append(txt)
    return lines


def _ocr_frame(bgr: np.ndarray) -> list[str]:
    return _ocr_bgr(bgr)


def _ocr_crop_zoom(bgr: np.ndarray) -> list[str]:
    """CROP-ZOOM OCR: 2x-upscaled full frame + a 3x2 tile grid, each OCR'd, to lift SMALL
    on-screen text that full-frame OCR drops (measured in the prior session: recovers
    'CHIGAN STATE', 'TURKS A', small HUD/clock/sign text). Deduped against nothing here — the
    caller dedups vs the full-frame lines. Kept modest (2x, one grid) to bound noise."""
    h, w = bgr.shape[:2]
    found: list[str] = []
    big = cv2.resize(bgr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    found.extend(_ocr_bgr(big, min_conf=0.35))
    th, tw = h // 2, w // 3
    for r in range(2):
        for c in range(3):
            tile = bgr[r * th:(r + 1) * th, c * tw:(c + 1) * tw]
            tile2 = cv2.resize(tile, (tw * 2, th * 2), interpolation=cv2.INTER_CUBIC)
            found.extend(_ocr_bgr(tile2, min_conf=0.4))
    return found


# ---- gemma3 vision (ollama, in-memory base64) ---------------------------------------------

_VLM_PROMPT = (
    "This is ONE frame from a person's first-person phone camera during their day. "
    "Describe concretely ONLY what is visible: objects with their colours/materials, any "
    "person and what they wear, food, vehicles, screens (say what is on the screen), and READ "
    "any text/brand/logo verbatim. Note if the wearer's own body is visible (self-view: their "
    "outfit, wrist accessories). Do NOT guess or add world knowledge. 1-6 short lines."
)


_CAPTION_PREAMBLE = ("here", "in this", "the image", "this image", "this is", "sure", "okay",
                     "based on", "i see", "the frame", "this frame")


def _clean_caption(cap: str) -> list[str]:
    """Drop the model's meta-preamble ('Here's a description...') and keep concrete content
    lines, so scene captions carry observations, not chatter."""
    out: list[str] = []
    for raw in cap.splitlines():
        line = raw.strip().strip("-•*").strip()
        low = line.lower()
        if len(line) < 4 or low.endswith(":"):
            continue
        if any(low.startswith(p) for p in _CAPTION_PREAMBLE):
            continue
        out.append(line[:220])
    return out


def _vlm_frame(bgr: np.ndarray, model: str, timeout: int = 300) -> str:
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return ""
    b64 = base64.b64encode(buf.tobytes()).decode()
    body = {"model": model, "prompt": _VLM_PROMPT, "images": [b64],
            "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(f"{HOST}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()
    except Exception as exc:  # noqa: BLE001
        print(f"    ! VLM error: {exc}", flush=True)
        return ""


# ---- Whisper dense-window ASR (recovers short utterances Whisper LM-smooths away) ----------

def _asr(video: Path, model_name: str = "small.en") -> list[tuple[float, str]]:
    import whisper
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "audio.wav"
        subprocess.run(["ffmpeg", "-y", "-i", str(video), "-ar", "16000", "-ac", "1",
                        str(wav)], check=True, capture_output=True)
        model = whisper.load_model(model_name)
        # Whole-track pass + overlapping 6s windows @2s hop with no cross-window conditioning,
        # so a 1-word greeting ("Okay Joe") isn't smoothed into the surrounding sentence.
        out: dict[float, str] = {}
        full = model.transcribe(str(wav), language="en", condition_on_previous_text=False)
        for seg in full.get("segments", []):
            out[round(seg["start"], 1)] = seg["text"].strip()
        audio = whisper.load_audio(str(wav))
        dur = len(audio) / 16000.0
        t = 0.0
        while t < dur:
            clip = audio[int(t * 16000):int((t + 6) * 16000)]
            if len(clip) < 16000:
                break
            r = model.transcribe(clip, language="en", condition_on_previous_text=False)
            txt = r.get("text", "").strip()
            if txt and len(txt) >= 3:
                out.setdefault(round(t, 1), txt)
            t += 2.0
    return sorted(out.items())


# ---- frame selection -----------------------------------------------------------------------

def _keyframes(video: Path, fps: float, max_vlm: int) -> list[tuple[int, float, np.ndarray, bool]]:
    """Sample at `fps`, return (index, t_seconds, bgr, is_vlm_keyframe). VLM keyframes are the
    top-`max_vlm` scene changes (mean abs frame diff) so a montage's ~17 distinct scenes are
    covered without VLM'ing every near-duplicate. OCR runs on ALL sampled frames (cheap)."""
    cap = cv2.VideoCapture(str(video))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(src_fps / fps)))
    sampled: list[tuple[int, float, np.ndarray]] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            sampled.append((i, i / src_fps, frame))
        i += 1
    cap.release()
    prev = None
    scored: list[tuple[float, int]] = []
    for pos, (_fi, _t, f) in enumerate(sampled):
        small = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (64, 64)).astype(int)
        diff = 255.0 if prev is None else float(np.mean(np.abs(small - prev)))
        scored.append((diff, pos))
        prev = small
    keep = {pos for _d, pos in sorted(scored, reverse=True)[:max_vlm]}
    return [(fi, t, f, pos in keep) for pos, (fi, t, f) in enumerate(sampled)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "data/phone_captures/Day in the life.mp4"))
    ap.add_argument("--store", default=str(ROOT / "evaluation/day_in_life/day_in_life.sqlite3"))
    ap.add_argument("--fps", type=float, default=1.5)
    ap.add_argument("--vlm-model", default="gemma3:12b-it-qat")
    ap.add_argument("--max-vlm", type=int, default=48)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    video = Path(args.video)
    store_path = Path(args.store)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.resume and store_path.exists():
        store_path.unlink()
    hub = Hub(str(store_path))

    done_frames = set()
    if args.resume:
        for node in hub.store.nodes(node_types=("observation",), sources=("phone_camera",)):
            fi = (node.metadata or {}).get("frame_index")
            if fi is not None:
                done_frames.add(int(fi))
        print(f"resume: {len(done_frames)} frames already perceived", flush=True)

    frames = list(_keyframes(video, args.fps, args.max_vlm))
    n_key = sum(1 for f in frames if f[3])
    print(f"{len(frames)} sampled frames, {n_key} VLM keyframes @ {args.vlm_model}", flush=True)

    def put(text: str, source: str, t_ms: int, frame_index: int, extra=None):
        meta = {"frame_index": frame_index}
        if extra:
            meta.update(extra)
        hub.ingest({"memory_text": text, "source": source, "timestamp": _iso(t_ms),
                    "source_type": "audio" if source == "apple_speech" else "vision",
                    "metadata": meta})

    def _clean_ocr_line(s: str) -> str:
        return " ".join(s.split()).strip()

    # 1) OCR on all sampled frames + VLM on keyframes
    for fi, t, bgr, is_key in frames:
        if fi in done_frames:
            continue
        t_ms = BASE_MS + int(t * 1000)
        lines = [_clean_ocr_line(x) for x in _ocr_frame(bgr)]
        if is_key:
            # crop-zoom recovers small text; merge NEW lines (case-insensitive dedup)
            have = {x.lower() for x in lines}
            for x in (_clean_ocr_line(y) for y in _ocr_crop_zoom(bgr)):
                if x and x.lower() not in have:
                    have.add(x.lower())
                    lines.append(x)
        lines = [x for x in lines if len(x) >= 3 and any(ch.isalnum() for ch in x)]
        if lines:
            # ONE blob row for context (kept short) ...
            put(f'OBJECT | screen text | OCR text: "{" | ".join(lines[:14])[:400]}"',
                "vision_ocr", t_ms, fi)
            # ... PLUS one row per distinct line, so a specific token (a lecturer name, a
            # university, a clock) is individually retrievable instead of buried in the blob
            # (the Q1 'maccombs is present but the wrong OCR blob ranked' failure).
            for line in lines[:14]:
                if len(line) >= 4:
                    put(f'OBJECT | screen text | reads "{line}"', "vision_ocr", t_ms, fi,
                        extra={"ocr_line": True})
        if is_key:
            cap = _vlm_frame(bgr, args.vlm_model)
            if cap:
                for line in _clean_caption(cap)[:6]:
                    put(f"OBJECT | scene | {line}", "fastvlm", t_ms, fi)
            print(f"  frame {fi} t={t:5.1f}s  ocr={len(lines):2}  vlm={'Y' if cap else '-'}",
                  flush=True)

    # 2) ASR over the whole track (once)
    if not any(_n for _n in hub.store.nodes(node_types=("observation",), sources=("phone_camera",))
               if (_n.metadata or {}).get("helper") == "asr"):
        print("ASR (Whisper dense windows)...", flush=True)
        for t, text in _asr(video):
            put(f'EVENT | nearby speech | transcript: "{text}"', "apple_speech",
                BASE_MS + int(t * 1000), -1)
            print(f"  asr t={t:5.1f}s  {text[:60]}", flush=True)

    print(f"\nperceived -> {store_path}  ({hub.store.node_count()} nodes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
