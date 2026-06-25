#!/usr/bin/env python3
"""Mac-side perception: run the local multimodal gemma3 over the phone's streamed
frames. FastVLM (the tiny on-device VLM) parrots its prompt and can't perceive; the
Mac's gemma3:12b is a strong vision model and runs locally. This is the two-tier fix:
gemma-VISION perceives each frame -> gemma-TEXT consolidates across frames (consensus)
into one combined scene (physical items AND on-screen/laptop content) -> answer.

    .venv/bin/python scripts/mac_vision_perceive.py <frames_dir> [--n 6] [--ask "q1" "q2"]
"""
from __future__ import annotations

import argparse
import base64
import json
import urllib.request
from pathlib import Path

HOST = "http://127.0.0.1:11434"
MODEL = "gemma3:12b-it-qat"


def _gen(prompt: str, images: list[str] | None = None, timeout: int = 240) -> str:
    body = {"model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0}}
    if images:
        body["images"] = images
    req = urllib.request.Request(f"{HOST}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()


def perceive_frame(path: Path) -> str:
    img = base64.b64encode(path.read_bytes()).decode()
    prompt = (
        "This is one frame from a person's first-person camera (a live feed). "
        "List what is actually visible, concisely. Name brands/products whose label "
        "is legible. If a laptop/phone/TV screen is visible, say it's a screen and "
        "what is on it. Only what you see — do not guess. 1-5 short bullet lines."
    )
    return _gen(prompt, images=[img])


def consolidate(per_frame: list[str]) -> str:
    """Fuse independent per-frame descriptions into one scene; an item in multiple
    frames is reliable, a one-off is uncertain. Physical + on-screen kept, labeled."""
    if not per_frame:
        return ""
    joined = "\n\n".join(f"FRAME {i+1}:\n{d}" for i, d in enumerate(per_frame))
    return _gen(
        "Below are independent descriptions of consecutive frames from one live "
        "first-person capture. Consolidate them into ONE scene. An item seen in "
        "MULTIPLE frames is reliably present; an item in only one frame is uncertain "
        "(say so). Keep PHYSICAL items and ON-SCREEN content (a laptop/phone screen "
        "and what's on it) as separate labeled groups, but include both. Do not invent.\n\n"
        f"{joined}\n\nCONSOLIDATED SCENE:"
    )


def answer(scene: str, question: str) -> str:
    if not scene:
        return "I haven't perceived anything yet."
    return _gen(
        "Answer ONLY from this scene. If it's not there, say you don't have it. "
        "On-screen content counts as something the person saw.\n\n"
        f"SCENE:\n{scene}\n\nQUESTION: {question}\nANSWER:"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--ask", nargs="*", default=[
        "What did I see?", "What chocolate was there?",
        "What is the flavour of the pesto?", "Was there a laptop and what was on it?",
    ])
    args = ap.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.jpg"), key=lambda p: int(p.stem.split(".")[0]))
    if not frames:
        print("no frames")
        return 1
    step = max(1, len(frames) // args.n)
    sample = frames[::step][: args.n]
    print(f"perceiving {len(sample)} of {len(frames)} frames with {MODEL}-vision...\n")

    per_frame = []
    for p in sample:
        desc = perceive_frame(p)
        per_frame.append(desc)
        print(f"--- {p.name} ---\n{desc}\n")

    joined = "\n\n".join(f"FRAME {i+1}:\n{d}" for i, d in enumerate(per_frame))
    scene = _gen(
        "Below are independent descriptions of consecutive frames from one live "
        "first-person capture. Consolidate them into ONE scene. An item seen in "
        "MULTIPLE frames is reliably present; an item in only one frame is uncertain "
        "(say so). Keep PHYSICAL items and ON-SCREEN content (a laptop/phone screen "
        "and what's on it) as separate labeled groups, but include both. Do not invent.\n\n"
        f"{joined}\n\nCONSOLIDATED SCENE:"
    )
    print("=" * 60)
    print("CONSOLIDATED SCENE:\n" + scene + "\n")

    for q in args.ask:
        ans = _gen(
            "Answer ONLY from this scene. If it's not there, say you don't have it. "
            "On-screen content counts as something the person saw.\n\n"
            f"SCENE:\n{scene}\n\nQUESTION: {q}\nANSWER:"
        )
        print(f"Q: {q}\n  A: {ans}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
