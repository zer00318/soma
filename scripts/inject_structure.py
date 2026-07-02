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
    """Normalize a VLM-produced entity name for display."""
    n = name.strip().strip('"').strip("'").strip().lower()
    n = re.sub(r"^(a |an |the |visible |some |several |part of |portion of )", "", n)
    n = re.sub(r"^\d+\s+", "", n)          # "3 jars" -> "jars" (count claim, not identity)
    n = re.sub(r"s$", "", n) if len(n) > 4 else n   # crude singularize
    return n.strip()


_ROOT_NOUNS = {
    "rings": "ring", "ring": "ring",
    "jars": "jar", "jar": "jar",
    "laptops": "laptop", "laptop": "laptop", "laptop/computer": "laptop",
    "spoons": "spoon", "spoon": "spoon",
    "bottles": "bottle", "bottle": "bottle",
    "books": "book", "book": "book", "notebook": "book",
    "tables": "table", "table": "table",
    "shelf": "shelf", "shelves": "shelf",
    "cable": "cable", "cables": "cable", "cord": "cable",
    "charger": "charger", "chargers": "charger",
    "pesto": "pesto", "nutella": "nutella", "barilla": "barilla",
}


def _merge_key(name: str) -> str:
    """Derive a merge key for consensus counting. Different descriptions of the
    same entity should produce the same key: 'jar labeled Nutella', 'jars of nutella',
    'Nutella jar' -> 'jar nutella'. '3 rings (one silver...)' and 'Two rings' -> 'ring'."""
    n = name.strip().strip('"').strip("'").strip().lower()
    n = re.sub(r"^(a |an |the |visible |some |several |part of |portion of )", "", n)
    n = re.sub(r"^\d+\s+", "", n)
    n = re.sub(r"\s*\(.*?\)", "", n)
    n = re.sub(r"\s*(with|displaying|resting|plugged|attached|extending|covering)\s+.*", "", n)
    n = re.sub(r"\s*on\s+(top|its|the)\b.*", "", n)
    m = re.match(r"(.+?)\s+label(?:ed|led)\s+['\"]?(\w+)", n)
    if m:
        n = f"{m.group(1)} {m.group(2)}"
    m2 = re.match(r"(.+?)\s+of\s+(.+)", n)
    if m2:
        n = f"{m2.group(2)} {m2.group(1)}"
    words = re.findall(r"[a-zà-ÿ]{3,}", n)
    # Strip number-words and color-words (they're attributes, not identity)
    nums = {"one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "each", "some", "various", "multiple", "several",
            "including", "possibly", "likely", "appears"}
    words = [w for w in words if w not in nums]
    # Map to root nouns for merging
    rooted = sorted(set(_ROOT_NOUNS.get(w, w) for w in words))
    # Keep only the 2 most identity-bearing words to avoid over-splitting
    return " ".join(rooted[:2]) if rooted else n


# Surface/location tails describe an object's SURROUNDINGS, not the object. Leaving
# them in the entity name is how a 1-frame guess ("...on a grey tablecloth") becomes
# a falsely-asserted entity the brain then reports. Strip them from the display name.
_SURFACE_TAIL = re.compile(
    r"\s+(?:resting|sitting|placed|laying|lying|standing|positioned|mounted|perched|"
    r"on top of|on|atop|next to|in front of|behind|near|against|underneath|beneath)\b.*$",
    re.IGNORECASE,
)


def _best_name(raw_names: set[str], merge_key: str) -> str:
    """Pick the cleanest display name for a merged entity. Strips surface/location
    tails, then prefers the candidate carrying the most identity (merge_key) words,
    tie-broken by SHORTEST — a clean 'silver spoon' beats 'silver spoon resting on
    a grey tablecloth'."""
    if not raw_names:
        return merge_key
    key_words = set(merge_key.split())
    best, best_score = merge_key, (-1, 0)
    for raw in raw_names:
        cleaned = _SURFACE_TAIL.sub("", raw).strip().rstrip(",.")
        if not cleaned:
            continue
        low = cleaned.lower()
        hits = sum(1 for w in key_words if w in low)
        # more identity words is better; shorter is better (clean over verbose)
        score = (hits, -len(cleaned))
        if score > best_score:
            best, best_score = cleaned, score
    return best


def _parse_line(line: str) -> list[dict[str, str]]:
    """Parse a caption line into object records. FastVLM often dumps comma-separated
    lists like 'OBJECT | jar, spoon, laptop, charger' — split them into individual
    entities so each can be consensus-tracked independently."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2 or parts[0].upper() not in ("OBJECT", "EVENT"):
        return []
    kind = parts[0].upper()
    name_field = parts[1]
    attrs = parts[2] if len(parts) > 2 else ""
    items = [n.strip() for n in re.split(r",\s*(?:and\s+)?|(?:^|\s)and\s+", name_field) if n.strip()]
    if not items:
        return []
    results = []
    for item in items:
        clean = re.sub(r"^(a |an |the )", "", item.strip(), flags=re.IGNORECASE).strip()
        if not clean:
            continue
        results.append({
            "kind": kind,
            "name": clean,
            "attrs": attrs if len(items) == 1 else "",
            "relation": parts[3] if len(parts) > 3 else "",
            "certainty": parts[4] if len(parts) > 4 else "",
        })
    return results


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
            for p in _parse_line(ln)
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
            parsed = _parse_line(ln)
            if not parsed:
                # Parse mac_vision bullet points: "*   a MacBook laptop"
                bullet = re.match(r"^\s*[\*\-]\s+(.+)", ln)
                if bullet and r.get("source") == "mac_vision":
                    phrase = bullet.group(1).strip().rstrip(".")
                    # Don't split inside parentheses
                    phrase_no_parens = re.sub(r"\([^)]*\)", "", phrase)
                    items = re.split(r",\s*(?:and\s+)?|\s+and\s+", phrase_no_parens)
                    # If the original had parens, keep the full phrase as-is for single items
                    if "(" in phrase and len(items) <= 2:
                        items = [phrase]
                    for item in items:
                        name = _norm_name(item)
                        if not name or len(name) < 3:
                            continue
                        skip = ("here's what", "image", "visible", "present",
                                "following", "observation", "person")
                        if any(s in name for s in skip):
                            continue
                        if name in _SCREEN_DEVICES:
                            dropped["screen_device"] += 1
                            continue
                        key = _merge_key(item)
                        ent = objects[key]
                        ent["frames"].add(t)
                        ent["raw_names"].add(item.strip())
                continue
            for p in parsed:
                if p["kind"] != "OBJECT":
                    continue
                name = _norm_name(p["name"])
                if not name or name in ("text surface", "object"):
                    continue
                if name in _SCREEN_DEVICES:
                    dropped["screen_device"] += 1
                    continue
                key = _merge_key(p["name"])
                ent = objects[key]
                ent["frames"].add(t)
                ent["raw_names"].add(p["name"].strip())
                a = p["attrs"].strip()
                if a and a.lower() not in ("visible object", "yes", "detected"):
                    ent["attrs"].append(a)

        for line in ocr:  # nothing else; ocr handled above
            pass

    # Post-merge: if key A is a subset of key B's words, absorb A into B.
    # e.g. "pesto" is subset of "jar pesto" → merge.
    keys = list(objects.keys())
    for i, k1 in enumerate(keys):
        w1 = set(k1.split())
        for k2 in keys[i + 1:]:
            if k2 not in objects:
                continue
            w2 = set(k2.split())
            if w1 < w2 or w2 < w1:
                parent = k1 if w1 > w2 else k2
                child = k2 if w1 > w2 else k1
                if child not in objects or parent not in objects:
                    continue
                objects[parent]["frames"] |= objects[child]["frames"]
                objects[parent]["attrs"].extend(objects[child]["attrs"])
                objects[parent]["raw_names"] |= objects[child]["raw_names"]
                del objects[child]

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
        best_name = _best_name(ent["raw_names"], name)
        out_objects.append(
            {
                "name": _norm_name(best_name),
                "merge_key": name,
                "frames_seen": n,
                "confidence": conf,
                "attrs": sorted(set(ent["attrs"]))[:6],
                "raw_names": sorted(ent["raw_names"]),
                "t_span": [min(ent["frames"]), max(ent["frames"])],
            }
        )
    out_objects.sort(key=lambda o: o["frames_seen"], reverse=True)

    # OCR entity extraction: find product names/brands that recur across multiple
    # frames in the world text. A word appearing in 3+ OCR frames is a real label.
    ocr_words: dict[str, set] = defaultdict(set)
    for w in world_text:
        t = w.get("t")
        text = w.get("text", "")
        for token in re.findall(r"[A-Za-zÀ-ÿ]{3,}", text):
            ocr_words[token.lower()].add(t)
    ocr_entities = []
    noise = {"ocr", "text", "the", "and", "with", "for", "from", "that",
             "this", "are", "was", "has", "had", "not", "but", "grat",
             "grats", "gratis", "gran", "gra"}
    for word, frames in sorted(ocr_words.items(), key=lambda x: -len(x[1])):
        if word in noise or len(word) < 3:
            continue
        if len(frames) >= 3:
            ocr_entities.append({"text": word, "frames_seen": len(frames)})

    return {
        "objects": out_objects,
        "world_text": world_text,
        "on_screen": on_screen,
        "ocr_entities": ocr_entities,
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
    ocr_ents = scene.get("ocr_entities", [])
    if ocr_ents:
        lines.append("\nRECURRING LABEL TEXT (seen across multiple frames — reliable):")
        for e in ocr_ents[:15]:
            lines.append(f"  - \"{e['text']}\" (in {e['frames_seen']} frames)")
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
