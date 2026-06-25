#!/usr/bin/env python3
"""INJECT — turn the phone's loose, noisy derived text into a clean, bound scene.

The on-device tiny VLM is a LOOSE perceiver: it echoes prompt templates, stuffs
"yes", hallucinates one-off attributes, repeats lines, and reads on-screen text
(our own UI, a YouTube video) as if it were the physical world. The flat-string
memory has no quality floor, so the brain answers from that garbage.

This module is the quality floor + binder that was missing. It:
  1. PREFILTERS deterministic junk: prompt-template echoes, "yes|yes" filler,
     and lines that are clearly our own system text read off a screen.
  2. QUARANTINES screen content: OCR seen on a laptop/monitor (or matching known
     UI tokens) is tagged on_screen, NEVER treated as physical surroundings.
  3. CONSENSUS-BINDS entities: an object corroborated across many frames is real
     and high-confidence; a one-off ("3 jars", "the spoon") is low-confidence
     and dropped — this is what kills the hallucinations.
  4. Emits a typed scene {objects[], world_text[], on_screen[], dropped} with a
     confidence + frame provenance per object, for the brain to answer from.

Pure-stdlib; deterministic (no LLM). Run:
    .venv/bin/python scripts/inject_structure.py [kf_memory.json]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Lines the tiny VLM emits that are never real facts.
_ECHO = re.compile(
    r"<specific name>|<attributes>|<where in frame>|<certainty>"
    r"|^\s*object \| name \| attributes|^\s*name \| attributes",
    re.IGNORECASE,
)
# "yes | yes | yes" style filler where the model gave up and filled the schema.
_FILLER = re.compile(r"\|\s*yes\s*\|\s*yes\b", re.IGNORECASE)
# Our own system/diagnostic text leaking in off a screen — never a world object.
_SYSTEM_TOKENS = (
    "yolo", "coco", "floods memory", "sports ball", "richest channel",
    "fastvilm", "fastvlm stable", "detector floods", "semantic refresh",
)
# Devices whose surface text is SCREEN content, not the physical environment.
_SCREEN_DEVICES = {
    "laptop", "monitor", "display screen", "screen", "computer", "tv",
    "television", "keyboard", "mouse", "remote control", "speaker", "cell phone",
}
# UI / app chrome strings that mark OCR as on-screen rather than a product label.
_UI_TOKENS = (
    "claude", "bypass permissions", "type / for commands", "chief/", "esc ",
    "session status", "file edit view", "cowork", "youtube", "subscribe",
    "option command", "dispatch background", "create pr",
)


def _norm_name(name: str) -> str:
    n = name.strip().strip('"').strip().lower()
    n = re.sub(r"^(a |an |the |visible |some )", "", n)
    n = re.sub(r"^\d+\s+", "", n)          # "3 jars" -> "jars" (count claim, not identity)
    n = re.sub(r"s$", "", n) if len(n) > 4 else n   # crude singularize
    return n.strip()


def _parse_line(line: str) -> dict[str, str] | None:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2 or parts[0].upper() not in ("OBJECT", "EVENT"):
        return None
    return {
        "kind": parts[0].upper(),
        "name": parts[1],
        "attrs": parts[2] if len(parts) > 2 else "",
        "relation": parts[3] if len(parts) > 3 else "",
        "certainty": parts[4] if len(parts) > 4 else "",
    }


def build_scene(records: list[dict[str, Any]]) -> dict[str, Any]:
    objects: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"frames": set(), "attrs": [], "raw_names": set()}
    )
    world_text: list[dict[str, Any]] = []
    on_screen: list[dict[str, Any]] = []
    dropped = {"echo": 0, "filler": 0, "system_text": 0, "screen_device": 0}

    # Pass 1: decide which frames are "screen frames" — looking at a laptop/monitor,
    # or whose text matches our own UI/system chrome. ALL OCR in such a frame is
    # on-screen content, not the physical environment.
    screen_frames: set[Any] = set()
    for r in records:
        t = r.get("t")
        names_here = [
            _norm_name(p["name"])
            for ln in (r.get("caption") or "").splitlines()
            if (p := _parse_line(ln))
        ]
        ocr_blob = " ".join(r.get("ocr") or []).lower()
        if (
            any(n in _SCREEN_DEVICES for n in names_here)
            or any(tok in ocr_blob for tok in _UI_TOKENS)
            or any(tok in ocr_blob for tok in _SYSTEM_TOKENS)
        ):
            screen_frames.add(t)

    for r in records:
        t = r.get("t")
        cap = r.get("caption") or ""
        ocr = r.get("ocr") or []
        lines = [ln for ln in cap.splitlines() if ln.strip()]

        # Route OCR by frame context: screen frame -> quarantine, else world label.
        for line in ocr:
            (on_screen if t in screen_frames else world_text).append(
                {"t": t, "text": line}
            )

        for ln in lines:
            low = ln.lower()
            if _ECHO.search(ln):
                dropped["echo"] += 1
                continue
            if _FILLER.search(ln):
                dropped["filler"] += 1
                continue
            if any(tok in low for tok in _SYSTEM_TOKENS):
                dropped["system_text"] += 1
                continue
            p = _parse_line(ln)
            if not p or p["kind"] != "OBJECT":
                continue
            name = _norm_name(p["name"])
            if not name or name in ("text surface", "object"):
                continue
            if name in _SCREEN_DEVICES:
                dropped["screen_device"] += 1
                continue
            ent = objects[name]
            ent["frames"].add(t)
            ent["raw_names"].add(p["name"].strip())
            a = p["attrs"].strip()
            if a and a.lower() not in ("visible object", "yes", "detected"):
                ent["attrs"].append(a)

        for line in ocr:  # nothing else; ocr handled above
            pass

    total_frames = len({r.get("t") for r in records}) or 1
    out_objects = []
    for name, ent in objects.items():
        n = len(ent["frames"])
        # Consensus confidence: corroboration across independent frames. A tiny VLM
        # hallucinates the SAME ghost across 1-2 frames, so the assertion bar is high
        # (>=6 = trust, 4-5 = hedge, <=3 = noise, not asserted). This is what keeps a
        # 2-frame ghost ("spoon") from ever being claimed as seen.
        # Bar scales with capture length: a real object recurs across a meaningful
        # share of frames; a 1-frame ghost never asserts. (Short captures would
        # starve under a fixed high bar.)
        hi = max(4, round(0.18 * total_frames))
        if n >= hi:
            conf = "high"
        elif n >= max(2, round(0.08 * total_frames)):
            conf = "medium"
        else:
            conf = "low"
        out_objects.append(
            {
                "name": name,
                "frames_seen": n,
                "confidence": conf,
                "attrs": sorted(set(ent["attrs"]))[:6],
                "t_span": [min(ent["frames"]), max(ent["frames"])],
            }
        )
    out_objects.sort(key=lambda o: o["frames_seen"], reverse=True)
    return {
        "objects": out_objects,
        "world_text": world_text,
        "on_screen": on_screen,
        "dropped": dropped,
        "total_frames": total_frames,
    }


def _scene_brief(scene: dict[str, Any]) -> str:
    """Render the cleaned scene for the brain — physical objects with their
    consensus strength, real product text, and quarantined on-screen text."""
    lines = ["PHYSICAL OBJECTS ACTUALLY SEEN (with how many frames corroborate each):"]
    for o in scene["objects"]:
        if o["confidence"] == "low":
            continue
        a = f" — attributes guessed by the camera (may be wrong): {'; '.join(o['attrs'])}" if o["attrs"] else ""
        lines.append(f"  - {o['name']} (seen in {o['frames_seen']} frames, {o['confidence']} confidence){a}")
    seen = set()
    wt = []
    for w in scene["world_text"]:
        k = re.sub(r"\s+", " ", w["text"]).strip().lower()[:50]
        if k and k not in seen:
            seen.add(k)
            wt.append(w["text"][:120])
    lines.append("\nREADABLE TEXT ON PHYSICAL OBJECTS (labels/signs):")
    lines += [f"  - {t}" for t in wt[:12]] or ["  (none)"]
    lines.append(f"\nON-SCREEN CONTENT the wearer was looking at ({len(scene['on_screen'])} fragments) — "
                 "this is a SCREEN/VIDEO, NOT the physical surroundings; ignore unless asked about a screen/video.")
    return "\n".join(lines)


def answer_from_scene(scene: dict[str, Any], question: str,
                      host: str = "http://127.0.0.1:11434",
                      model: str = "gemma3:12b-it-qat") -> str:
    import urllib.request

    brief = _scene_brief(scene)
    sys_prompt = (
        "You answer questions about what a person saw, using ONLY the cleaned scene below. "
        "Rules: (1) For 'what am I looking at / what do I see / what's around me', LIST the "
        "physical objects (high/medium confidence) by name — that is the answer, do not refuse. "
        "(2) Only state things supported by the PHYSICAL OBJECTS or their readable text. "
        "(3) An object's guessed attributes may be wrong — do NOT report an attribute that makes "
        "no sense for that object (a Pringles can is not a spoon; tortillas are not a flavour). "
        "(4) frames-seen is corroboration strength, NOT a count of items; never turn it into a "
        "count, and never invent a count. If asked 'how many' and you cannot be sure, say you saw "
        "at least one but cannot reliably count. (5) On-screen/video content is NOT the physical "
        "surroundings; only use it if asked about a screen/video. (6) If a specific asked-for thing "
        "(a spoon, a pesto) is not in the objects, say: \"I don't have that in what I actually "
        "saw.\" Be concise and concrete."
    )
    prompt = f"{sys_prompt}\n\nCLEANED SCENE:\n{brief}\n\nQUESTION: {question}\nANSWER:"
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=body,
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))["response"].strip()


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/phone_captures/live/kf_memory.json"
    records = json.load(open(path))
    scene = build_scene(records)
    print(f"=== SCENE from {Path(path).name} ({scene['total_frames']} frames) ===")
    print("\nPHYSICAL OBJECTS (consensus-bound):")
    for o in scene["objects"]:
        print(f"  [{o['confidence']:>6}] {o['name']:<22} seen {o['frames_seen']:>2} frames"
              f"  {('· ' + '; '.join(o['attrs'])) if o['attrs'] else ''}")
    print(f"\nWORLD TEXT (real labels, {len(scene['world_text'])}):")
    seen = set()
    for w in scene["world_text"]:
        k = w["text"][:40].lower()
        if k in seen:
            continue
        seen.add(k)
        print(f"  [{w['t']}s] {w['text'][:90]}")
    print(f"\nQUARANTINED ON-SCREEN ({len(scene['on_screen'])}) — NOT physical surroundings")
    print(f"DROPPED NOISE: {scene['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
