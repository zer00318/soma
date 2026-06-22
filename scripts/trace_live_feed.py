#!/usr/bin/env python3
"""TRACE live feed — Mac-side spine: ONE window -> local VLM -> brain (no raw media).

The founder is at home, so a Brave window playing a first-person POV walking
video stands in for the world ("as if I'm walking live"). This sampler captures
ONLY that one window (matched by its title, via Quartz — never the whole screen,
never another tab), sends each frame to a LOCAL vision model (Ollama gemma3) for
derived text (scene + objects + verbatim on-screen text), POSTs that text to the
TRACE brain's live stream, and discards the pixels in memory. Nothing raw ever
touches disk: the no-surveillance moat holds by construction.

    .venv/bin/python scripts/trace_live_feed.py --duration 90 --every 4

Pair with a window launched chromeless so its title is the page <title>:
    open -na "Brave Browser" --args --user-data-dir=/tmp/trace_brave_profile \
        --app=file:///.../data/live/_embed/live.html --window-size=1280,800
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import subprocess
import sys
import time
import urllib.request
from typing import Optional

import Quartz
from CoreFoundation import CFDataGetBytes, CFDataGetLength

DEFAULT_TITLE = "TRACE live view"
DEFAULT_MODEL = "gemma3:12b-it-qat"
DEFAULT_BRAIN = "http://127.0.0.1:8765"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"

PERCEIVE_PROMPT = (
    "You are a person's first-person camera walking through the world. Report ONLY "
    "what is actually visible in THIS frame — never guess or carry over. Output exactly:\n"
    "SCENE: <one short sentence>\n"
    "OBJECTS: <comma-separated concrete things you actually see>\n"
    "TEXT: <any on-screen/sign text copied verbatim, or NONE>\n"
    "PEOPLE: <count and what they appear to be doing, or NONE>"
)


def trace_brave_pids(profile: str = "trace_brave_profile") -> set[int]:
    """PIDs of the dedicated TRACE Brave (main process only, not --type= helpers).

    Matching by profile/PID is robust to the window title changing to the video's
    name and to the window living on an inactive Mission Control space — and it
    guarantees we never capture the founder's personal Brave tabs.
    """
    pids: set[int] = set()
    try:
        out = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    except Exception:
        return pids
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, cmd = line.partition(" ")
        if profile in cmd and "--type=" not in cmd:
            try:
                pids.add(int(pid_str))
            except ValueError:
                continue
    return pids


def find_window(title: str, pids: Optional[set[int]] = None) -> Optional[dict]:
    """Return the TRACE window (largest match), searching ALL spaces.

    Prefer matching by the TRACE Brave PID set (robust). Fall back to a title
    substring match. Windows on inactive spaces still composite live frames.
    """
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    cands = []
    for w in wins:
        b = w.get("kCGWindowBounds", {}) or {}
        if b.get("Height", 0) <= 150:
            continue
        name = w.get("kCGWindowName", "") or ""
        pid = w.get("kCGWindowOwnerPID")
        match = (pids and pid in pids) or (title and title.lower() in name.lower())
        if match:
            cands.append((b.get("Width", 0) * b.get("Height", 0), w))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


# High-confidence verbatim-text channel: Apple Vision OCR (in-memory, no disk).
try:
    import os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from evaluation.vision_ocr import ocr_cgimage
except Exception:  # OCR optional; fall back to the VLM TEXT line if unavailable
    ocr_cgimage = None


def merge_ocr(vlm_text: str, ocr_lines) -> str:
    """Verbatim TEXT comes ONLY from the high-confidence Vision OCR channel.

    ocr_lines is None  -> OCR unavailable: keep the VLM text (graceful fallback).
    ocr_lines is a list -> OCR is authoritative: use it, or TEXT: NONE if it read
    nothing. We never let the VLM's guessed text stand when OCR is available, so
    unreadable (e.g. cursive) text becomes an honest refusal, not a fabrication.
    """
    if ocr_lines is None:
        return vlm_text
    ocr_str = " | ".join(s.strip() for s in ocr_lines if s.strip())
    text_line = f"TEXT: {ocr_str}" if ocr_str else "TEXT: NONE"
    out, replaced = [], False
    for line in vlm_text.splitlines():
        if line.upper().startswith("TEXT:"):
            out.append(text_line)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(text_line)
    return "\n".join(out)


def capture_window_jpeg(win_id: int, max_w: int = 768, quality: int = 70) -> tuple:
    """Composite ONLY this window's pixels (privacy: never the rest of the screen)."""
    cgimg = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        win_id,
        Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution,
    )
    if cgimg is None:
        raise RuntimeError("window capture returned None")
    w = Quartz.CGImageGetWidth(cgimg)
    h = Quartz.CGImageGetHeight(cgimg)
    if w == 0 or h == 0:
        raise RuntimeError("empty window image")
    # High-confidence verbatim text from Apple Vision OCR on the in-memory CGImage.
    # None = OCR unavailable (fall back to VLM); list (maybe empty) = OCR authoritative.
    ocr_lines = None
    if ocr_cgimage is not None:
        try:
            ocr_lines = ocr_cgimage(cgimg) or []
        except Exception:
            ocr_lines = None
    # CGImage -> PNG bytes via ImageIO, then hand to PIL for resize/JPEG.
    from Quartz import (
        CGImageDestinationCreateWithData,
        CGImageDestinationAddImage,
        CGImageDestinationFinalize,
    )
    from CoreFoundation import CFDataCreateMutable
    data = CFDataCreateMutable(None, 0)
    dest = CGImageDestinationCreateWithData(data, "public.png", 1, None)
    CGImageDestinationAddImage(dest, cgimg, None)
    CGImageDestinationFinalize(dest)
    length = CFDataGetLength(data)
    raw = CFDataGetBytes(data, (0, length), None)
    png = bytes(raw)
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue(), ocr_lines


def perceive(jpeg: bytes, model: str, ollama: str, timeout: int = 120) -> str:
    b64 = base64.b64encode(jpeg).decode()
    payload = {
        "model": model,
        "prompt": PERCEIVE_PROMPT,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 220},
    }
    req = urllib.request.Request(
        f"{ollama}/api/generate", data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("response", "").strip()


def post_perception(brain: str, moment: str, text: str, timeout: int = 10) -> dict:
    payload = {"moment_id": moment, "memory_text": text, "source": "live_screen",
               "scene_phase": "live"}
    req = urllib.request.Request(
        f"{brain}/capture/perception", data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser(description="TRACE live feed: one window -> local VLM -> brain")
    ap.add_argument("--title", default=DEFAULT_TITLE, help="window title substring to capture")
    ap.add_argument("--moment", default="live")
    ap.add_argument("--duration", type=float, default=90.0)
    ap.add_argument("--every", type=float, default=4.0)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--brain", default=DEFAULT_BRAIN)
    ap.add_argument("--ollama", default=DEFAULT_OLLAMA)
    ap.add_argument("--probe", action="store_true", help="capture one frame, perceive, print, exit")
    args = ap.parse_args()

    pids = trace_brave_pids()
    win = find_window(args.title, pids)
    if not win:
        print(f"[live_feed] no TRACE window found (pids={pids or 'none'}, "
              f"title~{args.title!r}). Launch the TRACE live window first.", file=sys.stderr)
        return 2
    win_id = win.get("kCGWindowNumber")
    b = win.get("kCGWindowBounds", {})
    print(f"[live_feed] capturing window {win_id} "
          f"{int(b.get('Width',0))}x{int(b.get('Height',0))} title={win.get('kCGWindowName')!r}",
          flush=True)

    if args.probe:
        jpeg, ocr = capture_window_jpeg(win_id)
        text = merge_ocr(perceive(jpeg, args.model, args.ollama), ocr)
        print(f"[probe] {len(jpeg)} bytes, {len(ocr)} OCR lines ->\n{text}")
        return 0

    start = time.monotonic()
    n_ok = n_err = 0
    next_t = start
    while time.monotonic() - start < args.duration:
        now = time.monotonic()
        if now < next_t:
            time.sleep(min(0.1, next_t - now))
            continue
        next_t += args.every
        # Re-find the window each tick (id can change if relaunched).
        win = find_window(args.title, pids)
        if not win:
            print("  [skip] window gone", flush=True)
            continue
        try:
            jpeg, ocr = capture_window_jpeg(win.get("kCGWindowNumber"))
            text = merge_ocr(perceive(jpeg, args.model, args.ollama), ocr)
            if not text:
                continue
            res = post_perception(args.brain, args.moment, text)
            t = res.get("t")
            head = text.replace("\n", " | ")[:100]
            print(f"  t={t}s frames={res.get('frames')} :: {head}", flush=True)
            n_ok += 1
        except Exception as exc:
            n_err += 1
            print(f"  [err] {exc}", file=sys.stderr, flush=True)
    print(f"[live_feed] done ok={n_ok} err={n_err} duration={args.duration}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
