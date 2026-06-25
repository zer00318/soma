#!/usr/bin/env python3
"""Temporal index over a watch-the-walk keyframe memory.

Reads a kf_memory.json (a LIST of records, each {t, frame, caption, ocr}),
classifies each keyframe into a COARSE subject class from BOTH its caption and
its OCR text, then turns each class's scattered sightings into time SPANS with
gap-tolerant merging — so an object that is visible across a stretch of the
walk counts the whole stretch, not just the frames that happened to be sampled.

This is the fix for the "how long on the laptop vs the posters" question. The
posters are sampled sparsely (the camera glances at each plaque for a frame or
two between platform/floor shots), so summing lone keyframes badly undercounts
them. Merging sightings that are separated by only a few seconds restores the
real dwell: a poster you walked past and looked at over a 30s stretch reads as
~30s, not 3 lone half-second blips.

Pure stdlib, deterministic, hand-inspectable — no model calls.

CLI:  python3 scripts/build_temporal_index.py <kf_memory.json>
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# ---------------------------------------------------------------------------
# Coarse subject classes.
#
# Each class is matched from BOTH the caption (what the VLM saw) and the OCR
# (text actually read off the object). We keep this a general, ordered table so
# the lead can eyeball it and so new walks classify without code changes:
# the FIRST class (in list order) that fires on a frame wins.
#
# Posters/signs/plaques are one visual class. Classification uses generic object
# and layout terms only; named OCR from an evaluation clip must never enter this
# table because that turns retrieval into an answer key.
# ---------------------------------------------------------------------------
CLASS_RULES = [
    {
        "label": "poster",
        # Caption words for a wall-mounted printed/displayed panel...
        "caption_kw": [
            "poster", "billboard", "signboard", "signpost", "street sign",
            "informational sign", "informational panel", "informational plaque",
            "information sign", "plaque", "mural", "exhibit", "museum exhibit",
            "digital display", "display mounted", "panel mounted",
            "sign mounted", "sign with the text", "sign with text",
            "subway station sign",
        ],
        # Generic OCR cues describe the medium, not the content of a known clip.
        "ocr_kw": [
            "poster", "sign", "plaque", "exhibit", "information",
        ],
        "ocr_re": [
            r"\b1[89]\d{2}\b",          # life-dates like 1845 - 1923 / 1881 - 1945
            r"\bbus\b",                  # transit signpost glyphs
        ],
    },
    {
        "label": "laptop",
        "caption_kw": [
            "laptop", "command-line", "command line", "command prompt",
            "command-prompt", "keyboard", "trackpad", "chat interface",
            "claude", "code or text", "code editor", "terminal",
        ],
        "ocr_kw": [
            "claude", "trace", "command", "prompt", "$ ", "sudo", "python",
            "welcome", "http",
        ],
        "ocr_re": [],
    },
]

# Map every other token to its own loose label too, so the CLI dump still shows
# the non-target scenery (cart / floor / door / platform) for honesty.
SCENERY_VOCAB = [
    "platform", "subway", "train station", "railway", "track",
    "shopping cart", "cart", "backpack", "trash", "floor", "wall",
    "door", "tile",
]

STOP = set(
    "the a an of in on at is are was were it its to for and with this that "
    "scene shows image depicts appears foreground background close-up view".split()
)

# Median inter-frame gap in the real walk (t steps ~0.5s). A lone-frame sighting
# still gets a small non-zero footprint so it isn't silently dropped to 0.
_LONE_FRAME_S = 0.5

# How big a gap (seconds) between two same-class sightings we still treat as
# "kept looking at the same thing" and bridge. The walk glances away (a platform
# or floor shot) for a few seconds between poster sightings; bridging those gaps
# is exactly the dwell fix. Kept modest so we don't fuse genuinely separate
# encounters.
_DEFAULT_MERGE_GAP_S = 8.0


def _ocr_join(rec):
    """Join a record's ocr list into one string, dropping empties. Robust to a
    missing or non-list ocr field."""
    ocr = rec.get("ocr") or []
    if not isinstance(ocr, list):
        ocr = [ocr]
    return "; ".join(str(x) for x in ocr if x and str(x).strip())


def _norm(s):
    """Lowercase + strip German diacritics so OCR cues match despite umlauts."""
    s = (s or "").lower()
    for a, b in (("ö", "o"), ("ä", "a"), ("ü", "u"), ("ß", "ss"),
                 ("é", "e"), ("è", "e")):
        s = s.replace(a, b)
    return s


def classify(rec):
    """Coarse subject class for ONE keyframe, from caption AND OCR.

    Returns a class label from CLASS_RULES if any cue fires (first rule in list
    order wins), else a loose scenery label, else the first salient caption
    token, else 'scene'. Deterministic and side-effect free.
    """
    cap = _norm(rec.get("caption"))
    ocr = _norm(_ocr_join(rec))

    for rule in CLASS_RULES:
        if any(kw in cap for kw in rule["caption_kw"]):
            return rule["label"]
        if ocr:
            if any(kw in ocr for kw in rule["ocr_kw"]):
                return rule["label"]
            if any(re.search(rx, ocr) for rx in rule["ocr_re"]):
                return rule["label"]

    for term in SCENERY_VOCAB:
        if term in cap:
            return term.split()[-1]

    for tok in cap.split():
        tok = tok.strip(".,;:!?()[]\"'")
        if len(tok) >= 4 and tok not in STOP:
            return tok
    return "scene"


def _t(rec):
    try:
        return float(rec.get("t"))
    except (TypeError, ValueError):
        return 0.0


def _merge_class_spans(times, merge_gap):
    """Given the SORTED sighting times of one class, merge them into spans,
    bridging any gap <= merge_gap. Returns a list of (start, end) pairs.

    A bridged gap counts toward the span's duration — that is the whole point:
    if you saw the poster at t=63.5 and again at t=72 with a couple of platform
    glances in between, you were dwelling on that wall for ~8.5s, not 1s.
    """
    spans = []
    if not times:
        return spans
    start = prev = times[0]
    for t in times[1:]:
        if (t - prev) <= merge_gap:
            prev = t
        else:
            spans.append((start, prev))
            start = prev = t
    spans.append((start, prev))
    return spans


def get_durations(kf_path, merge_gap=_DEFAULT_MERGE_GAP_S, min_episode=1.0,
                  max_gap=None):
    """Classify keyframes into coarse subjects and return gap-tolerant dwell.

    For each class we collect every sighting time, then merge sightings
    separated by <= merge_gap into spans, so an object visible across a stretch
    of the walk counts the stretch. Pure-stdlib; no model calls.

    Returns:
        {"total_s": float,
         "episodes": [ {"label": str, "start": float, "end": float,
                        "duration": float, "frames": [str], "t": float,
                        "sample_ocr": str} ... ],   # sorted by start
         "by_label": { label: total_duration_float } }

    Backward-compat: `max_gap` is accepted as an alias for `merge_gap` so older
    callers (build with the old kwarg) keep working. min_episode is reserved
    (no episode is dropped — the lead wants honesty).
    """
    if max_gap is not None:
        merge_gap = max_gap
    try:
        with open(kf_path) as f:
            records = json.load(f)
        if not isinstance(records, list) or not records:
            return {"total_s": 0.0, "episodes": [], "by_label": {}}
    except Exception:
        return {"total_s": 0.0, "episodes": [], "by_label": {}}

    records = sorted(records, key=_t)

    # 1) Classify every frame; bucket (t, frame, ocr) by class label.
    buckets = {}
    for rec in records:
        label = classify(rec)
        buckets.setdefault(label, []).append(
            (_t(rec), rec.get("frame"), _ocr_join(rec))
        )

    # 2) Per class, merge sightings into gap-tolerant spans -> episodes.
    episodes = []
    for label, sightings in buckets.items():
        sightings.sort(key=lambda x: x[0])
        times = [s[0] for s in sightings]
        for (start, end) in _merge_class_spans(times, merge_gap):
            members = [s for s in sightings if start <= s[0] <= end]
            sample_ocr = ""
            for _, _, o in members:
                if o:
                    sample_ocr = o
                    break
            dur = end - start
            episodes.append({
                "label": label,
                "start": start,
                "end": end,
                "duration": dur if dur > 0 else _LONE_FRAME_S,
                "frames": [m[1] for m in members],
                "t": start,
                "sample_ocr": sample_ocr,
            })

    episodes.sort(key=lambda e: e["start"])

    by_label = {}
    for ep in episodes:
        by_label[ep["label"]] = by_label.get(ep["label"], 0.0) + ep["duration"]

    total_s = _t(records[-1]) - _t(records[0])
    return {"total_s": total_s, "episodes": episodes, "by_label": by_label}


def main():
    ap = argparse.ArgumentParser(description="Temporal episode index over a kf_memory.json")
    ap.add_argument("memory", nargs="?", help="path to kf_memory.json (positional)")
    ap.add_argument("--memory", dest="memory_flag", default=None,
                    help="alternate way to pass the kf_memory.json path")
    ap.add_argument("--merge-gap", type=float, default=_DEFAULT_MERGE_GAP_S,
                    help="seconds gap between same-class sightings still bridged "
                         "into one span (default %.1f)" % _DEFAULT_MERGE_GAP_S)
    ap.add_argument("--max-gap", type=float, default=None,
                    help="alias for --merge-gap (back-compat)")
    args = ap.parse_args()

    kf_path = args.memory or args.memory_flag
    if not kf_path:
        ap.error("provide a kf_memory.json path (positional or --memory)")

    merge_gap = args.max_gap if args.max_gap is not None else args.merge_gap
    idx = get_durations(kf_path, merge_gap=merge_gap)
    print("total_s: %.1f" % idx["total_s"])
    for ep in idx["episodes"]:
        ocr = (ep["sample_ocr"] or "")[:60]
        print("%-9s %.1fs-%.1fs  (%.1fs)  [%d]  ocr: %s"
              % (ep["label"], ep["start"], ep["end"], ep["duration"],
                 len(ep["frames"]), ocr))
    print()
    print("by_label (desc):")
    for label, total in sorted(idx["by_label"].items(), key=lambda x: -x[1]):
        print("  %s: %.1fs" % (label, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
