#!/usr/bin/env python3
"""The 'what's interesting here' helper (founder's idea, 2026-06-26).

The enumerative helpers (detector -> instances -> attributes -> OCR) inventory the
EXPECTED: objects, their attributes, their printed text. They have a structural blind
spot for the UNEXPECTED — the most human-valuable context:
  - anomalies / conditions: dirt on a keyboard, a crack, a stain, wear, something out of place
  - salience: what a person would actually notice / remember in THIS frame
  - recognition: a known person / brand / landmark identified by APPEARANCE, not OCR text
    (the 'it looked up Kushal Mehra with no text on screen' case) -> world-knowledge enrich

This helper runs in PARALLEL with the others and only adds what they miss. Its output is
TIERED so it never contaminates ground truth: 'observed' (a concrete visible detail),
'recognized' (an entity named by appearance -> triggers a world-knowledge lookup, hedged),
'inferred' (speculative -> clearly hedged). The brain keeps tiers in separate zones, so an
interesting GUESS is never reported as something definitely seen.

    .venv/bin/python scripts/salience_helper.py <image> [--crop x0 y0 x1 y1]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import urllib.request
from pathlib import Path

from PIL import Image

OLLAMA = "http://127.0.0.1:11434"
MODEL = "gemma3:27b-it-qat"

INTEREST_PROMPT = (
    "You are the 'what's interesting here' helper for a wearable context engine. Other "
    "helpers already list objects, attributes, and printed text — do NOT repeat that "
    "inventory. Your job is to notice what they MISS:\n"
    "- anomalies / conditions: dirt, dust, wear, damage, a stain, something out of place\n"
    "- salient details a careful person would remark on\n"
    "- any ENTITY you RECOGNISE by appearance (a known person, brand, logo, landmark, "
    "product), even when no text names it\n"
    "Rules: one short line each, prefixed 'NOTE:'. If you are inferring or unsure, start "
    "the note with 'maybe' or 'looks like'. If you recognise a specific named entity, say "
    "'appears to be <name>' or 'recognised <brand> logo'. Only genuinely notable things — "
    "if nothing is notable, output 'NOTE: nothing unusual'."
)


def _gen(prompt: str, img: bytes, timeout: int = 180) -> str:
    b64 = base64.b64encode(img).decode()
    body = {"model": MODEL, "prompt": prompt, "images": [b64], "stream": False,
            "options": {"temperature": 0.2}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()


def _jpeg(im: Image.Image, max_side: int = 1024, q: int = 92) -> bytes:
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    b = io.BytesIO(); im.save(b, format="JPEG", quality=q)
    return b.getvalue()


def tier_salience(note: str) -> str:
    """Classify one salience note into a TIER so the brain can fence it:
      'recognized' — names/identifies a specific entity by appearance (a proper-noun
                     person, or a known brand/logo). Triggers world-knowledge lookup.
      'inferred'   — hedged/speculative ('maybe', 'looks like', 'might', 'could be')
                     with no specific named entity.
      'observed'   — a concrete visible detail/anomaly stated plainly.

    Recognition takes priority over hedging ('looks like the Eiffel Tower' -> recognized,
    but 'looks like a coffee stain' -> inferred). Default to 'observed'.
    """
    lower = note.lower()
    hedge_words = ("maybe", "looks like", "might", "could be", "possibly", "seems")
    has_hedge = any(h in lower for h in hedge_words)
    known = {"adidas", "nike", "apple", "eiffel tower", "kushal mehra",
             "samsung", "google", "starbucks", "mcdonald", "gucci", "prada"}
    has_entity = any(k in lower for k in known)
    if not has_entity:
        has_entity = bool(re.search(r"(?:appears to be|recognised?)\b", lower))
    if not has_entity:
        words = note.split()
        caps = [w for w in words if w[0:1].isupper() and w.lower() not in
                {"i", "a", "the", "an", "note:", "there", "it", "this", "that"}]
        has_entity = len(caps) >= 2 or any(len(w) > 1 and w[0].isupper() for w in caps
                                            if w.lower() not in hedge_words)
    if has_entity:
        return "recognized"
    if has_hedge:
        return "inferred"
    return "observed"


def extract_entity(note: str) -> str:
    """From a 'recognized' salience note, return the bare entity name to look up in the
    world-knowledge layer; '' if none. Examples:
      'appears to be the philosopher Kushal Mehra' -> 'Kushal Mehra'
      'recognised the Adidas logo' -> 'Adidas'
      'looks like the Eiffel Tower in the background' -> 'Eiffel Tower'
      'visible dust on the keyboard' -> ''
    Strip lead-ins ('appears to be', 'looks like', 'recognised', 'the', articles,
    role words like 'philosopher') and trailing words ('logo', 'in the background');
    keep the proper-noun / brand. Return '' when the note names no specific entity."""
    s = re.sub(r"(?i)^(NOTE:\s*)?", "", note).strip()
    s = re.sub(r"(?i)^(appears to be|looks like|recognised?|seems to be)\s+", "", s)
    s = re.sub(r"(?i)^(the|a|an)\s+", "", s)
    s = re.sub(r"(?i)^(philosopher|author|artist|musician|actor|director|scientist|politician)\s+", "", s)
    s = re.sub(r"(?i)\s+(logo|brand|sign|symbol|emblem)\s*$", "", s)
    s = re.sub(r"(?i)\s+in the (background|foreground|distance|corner|scene)\s*$", "", s)
    s = s.strip()
    if not s or not s[0].isupper():
        return ""
    words = s.split()
    entity = []
    for w in words:
        if w[0].isupper() or (entity and w.lower() in ("of", "the", "de", "von", "van")):
            entity.append(w)
        else:
            break
    return " ".join(entity) if entity else ""


def extract_salience(image_path: str, crop: tuple[int, int, int, int] | None = None) -> list[dict]:
    im = Image.open(image_path).convert("RGB")
    if crop:
        im = im.crop(crop)
    raw = _gen(INTEREST_PROMPT, _jpeg(im))
    notes = []
    for line in raw.splitlines():
        m = re.match(r"\s*NOTE:\s*(.+)", line, re.IGNORECASE)
        if not m:
            continue
        text = m.group(1).strip()
        if text.lower() in ("nothing unusual", "nothing notable", "none"):
            continue
        notes.append({"note": text, "tier": tier_salience(text)})
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--crop", nargs=4, type=int, default=None)
    args = ap.parse_args()
    notes = extract_salience(args.image, tuple(args.crop) if args.crop else None)
    print(f"=== salience: {Path(args.image).name} ===")
    for n in notes:
        print(f"  [{n['tier']:>10}] {n['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
