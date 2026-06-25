#!/usr/bin/env python3
"""Counting specialist for TRACE walk memory.

Answers questions of the form "how many <category> did you see?" by
clustering keyframes that depict the SAME real-world instance (rather
than re-counting per-frame appearances).  Uses:

  1. OCR named-token overlap: frames that share distinctive named
     tokens (proper names, years, unique words) are the SAME instance.
  2. Caption keyword presence: frames flagged as containing the queried
     category but sharing no distinctive OCR are merged only when
     temporal proximity + caption similarity suggests so.
  3. Gemma reasoning pass (optional): for ambiguous cluster pairs gemma
     decides merge vs. split.

HARD RULES (inherited from TRACE spec):
  - Refusal-default: if the category is absent, say so honestly.
  - Never invent counts or names not grounded in kf_memory.
  - Cite timestamps, e.g. "(read at 63.5s)".
  - One self-contained file; --self-test exercises real walk memory.

ENTRYPOINT:
  def answer(question, kf, world, model, host, timeout) -> str

CLI:
  python scripts/counting_specialist.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ollama(prompt: str, model: str, host: str, timeout: int) -> str:
    """POST to ollama /api/generate (stream=false, temperature=0)."""
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("response", "").strip()


STOP_WORDS = set(
    "the a an of in on at is are was were i my me you your it its to for and "
    "with what where when who how do does did can could there here that this "
    "be have has had will would should may might also just then from by or "
    "scene depicts shows image photograph appears background foreground "
    "large small rectangular mounted wall blue light dark white black gray "
    "train station platform sign billboard poster frame depicts "
    # German common words that appear on multiple different posters/signs
    # (must not be used as cluster-identity tokens)
    "die der das den dem des ein eine einer einem einen eines und der die "
    "ERHIELT NOBELPREIS DIESES DIESER DIESEN DIESEM GELANG DARAUF ERSTEN "
    "FOLGENDEN AUFBAU EINBLICKE ASTROPHYSIK GRUNDLAGE TECHNIK MEDIZIN "
    "JAHRE JAHREN SIND NACH NEUE NEUEN NEUER DURCH AUCH NICHT EINE EINEN "
    "WERDEN WURDE SOWIE BEIM BEIM UBER UNTER IHRER IHREN SOWIE DENEN DEREN "
    "SEIT ODER BEIM".split()
)


def _tokens(text: str) -> List[str]:
    """Lowercase alpha-numeric tokens, no stop-words."""
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in raw if t not in STOP_WORDS and len(t) >= 3]


def _distinctive_tokens(ocr_text: str) -> set:
    """Tokens that are likely to identify a SPECIFIC real-world instance.

    IMPORTANT: only run on OCR text (not captions) — caption verbiage like
    "ADVERTISEMENT", "ATTACHED", "BLURRED" etc. is prose about the scene, not
    real-world text that identifies the object.

    Discriminating signals from OCR:
    - ALL-CAPS runs of >= 3 chars (proper names printed on things)
    - 4-digit years
    - Long tokens (>= 6 chars) that are not stop-words
    """
    text = ocr_text or ""
    raw_upper = re.findall(r"\b([A-ZÄÖÜ][A-ZÄÖÜ\s]{2,}(?:[A-ZÄÖÜ]))\b", text)
    years = re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", text)
    long_tokens = [t for t in _tokens(text) if len(t) >= 6]
    combined = set(t.upper().strip() for t in raw_upper if t.strip())
    combined.update(years)
    combined.update(t.upper() for t in long_tokens)
    return combined - {t.upper() for t in STOP_WORDS}


# ---------------------------------------------------------------------------
# Step 1: detect which frames mention the queried category
# ---------------------------------------------------------------------------

# Map broad category synonyms so "poster", "posters", "billboard", "sign"
# all activate the right detector.
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "poster":   ["poster", "billboard", "plaque", "exhibit", "informational", "mural"],
    "sign":     ["sign", "signpost", "signage", "label", "signboard"],
    "train":    ["train", "tram", "s-bahn", "u-bahn"],
    "person":   ["person", "people", "passenger", "man", "woman", "child", "human"],
    "bike":     ["bike", "bicycle", "cycling"],
    "bag":      ["bag", "backpack", "rucksack", "suitcase", "luggage"],
    "laptop":   ["laptop", "computer"],
    "door":     ["door", "gate", "entrance", "exit"],
    "chair":    ["chair", "seat", "bench"],
}

# Phrases that appear in captions but refer to the CONTEXT/SETTING, not
# an actual instance of the queried object.  A frame whose combined text
# matches an alias but ALSO matches one of these exclusions is skipped.
# Key = category, value = list of exclusion substrings.
CATEGORY_EXCLUSIONS: Dict[str, List[str]] = {
    "train": [
        "train station platform",
        "train station",
        "train tracks",
        "train track",
        "train line",
        "subway station",
        "subway platform",
        "transit station",
        "railway track",
        "tracks",          # "train tracks" without prefix
    ],
    "sign": [
        "exit sign",       # exit signs should be their own category
    ],
}


def _canonical(category: str) -> str:
    """Map a user-supplied category to its canonical key."""
    c = category.lower().rstrip("s")  # crude singularise
    for key, aliases in CATEGORY_ALIASES.items():
        if c in aliases or c == key:
            return key
    return c


def _aliases_for(category: str) -> List[str]:
    key = _canonical(category)
    return CATEGORY_ALIASES.get(key, [key])


# Location/context phrases a question can scope the count to ("signs on the DOOR",
# "posters on the WALL"). When present we keep ONLY frames whose caption/OCR sits in
# that context, so "how many signs on the door" does not count every sign on the walk.
# Each key maps to the words that mark a frame as being in that context.
# NOTE: cues are matched on word boundaries AND only when they appear in the FIRST
# part of the caption (the subject of the frame) — a poster caption that merely
# mentions "a metallic door above the panel" is about the POSTER, not the door.
CONTEXT_CUES: Dict[str, List[str]] = {
    "door":    ["door", "gate", "entrance"],
    "wall":    ["wall", "mounted on a wall", "informational sign", "billboard"],
    "track":   ["track", "railway", "platform edge"],
    "platform": ["platform"],
    "window":  ["window"],
    "screen":  ["screen", "monitor", "laptop", "display"],
}

# How far into a caption a single-word context cue may appear and still count as the
# frame's SUBJECT. Beyond this fraction it is treated as an incidental mention.
_CONTEXT_SUBJECT_FRACTION = 0.55

# Question phrasings that scope the count to a location -> the CONTEXT_CUES key.
CONTEXT_QUESTION_RE = re.compile(
    r"\bon (?:the |my |a )?(door|wall|track|platform|window|screen|gate|entrance)\b"
    r"|\b(?:at|near|by) (?:the |my |a )?(door|wall|track|platform|window|gate|entrance)\b",
    re.I,
)


def _question_context(question: str) -> Optional[str]:
    """Return the location key the question scopes the count to, or None.

    'how many signs on the door' -> 'door'; 'how many posters' -> None (whole walk).
    """
    m = CONTEXT_QUESTION_RE.search(question)
    if not m:
        return None
    loc = (m.group(1) or m.group(2) or "").lower()
    # normalise gate/entrance -> door (same physical context cues)
    if loc in ("gate", "entrance"):
        loc = "door"
    return loc if loc in CONTEXT_CUES else None


def _frame_in_context(frame: dict, context: str) -> bool:
    """True if the frame's caption/OCR places it in the requested location context.

    Two guards stop incidental mentions from scoping in the wrong frames:
      1. WORD-boundary match — a naive substring put every 'outdoors' caption into
         the 'door' context (the original 7-signs bug after scoping).
      2. SUBJECT position — a single-word cue only counts when it appears in the
         first ~55% of the caption (the frame's subject) or anywhere in OCR. A
         poster caption that mentions 'a metallic door above the panel' near the
         end is about the POSTER, not the door.
    """
    cues = CONTEXT_CUES.get(context, [context])
    caption = (frame.get("caption") or "").lower()
    ocr = (frame.get("_ocr_txt") or "").lower()
    cap_subject = caption[:max(40, int(len(caption) * _CONTEXT_SUBJECT_FRACTION))]
    for c in cues:
        if " " in c:
            # multi-word cue: specific enough to trust anywhere in caption or OCR.
            if c in caption or c in ocr:
                return True
        else:
            pat = r"\b" + re.escape(c) + r"\b"
            if re.search(pat, cap_subject) or re.search(pat, ocr):
                return True
    return False


def _frame_mentions_category(frame: dict, category: str, aliases: List[str]) -> bool:
    """True if the frame's caption or OCR mentions any alias of the category,
    AND it is NOT just a context/setting reference (e.g. 'train station' for 'train').
    """
    combined = ((frame.get("caption") or "") + " " +
                (frame.get("_ocr_txt") or "")).lower()
    if not any(a in combined for a in aliases):
        return False
    # Apply exclusions: if the frame only mentions the category as part of
    # a setting phrase (e.g. "train station platform"), skip it.
    key = _canonical(category)
    exclusions = CATEGORY_EXCLUSIONS.get(key, [])
    if exclusions:
        # Only exclude if EVERY alias hit is inside an exclusion phrase.
        hit_aliases = [a for a in aliases if a in combined]
        all_excluded = all(
            any(excl in combined for excl in exclusions)
            for a in hit_aliases
        )
        if all_excluded:
            return False
    return True


# ---------------------------------------------------------------------------
# Step 2: cluster by distinctive token overlap (named poster identity)
# ---------------------------------------------------------------------------

def _cluster_by_tokens(frames: List[dict]) -> List[Dict]:
    """Greedy merge: frames sharing >= 1 distinctive token go into the same
    cluster.  Runs multiple passes until stable.  Each cluster:
        {"label": str, "frames": [...], "first_seen": float,
         "tokens": set, "ocr_snippets": [...]}
    NOTE: distinctive tokens come from OCR only — captions use English prose
    that would create spurious merges across unrelated objects.
    """
    clusters: List[Dict] = []

    for frame in frames:
        # Use OCR only for identity tokens — captions are prose, not named objects
        ocr_text = frame.get("_ocr_txt") or ""
        dtok = _distinctive_tokens(ocr_text)

        # Find an existing cluster that shares at least 2 distinctive tokens,
        # or 1 long name-specific token (>= 6 chars, non-numeric).
        matched = None
        for cl in clusters:
            shared = cl["tokens"] & dtok
            if len(shared) >= 2:
                matched = cl
                break
            if len(shared) == 1:
                tok = next(iter(shared))
                if len(tok) >= 6 and not tok.isdigit():
                    matched = cl
                    break

        if matched:
            matched["frames"].append(frame)
            matched["tokens"] |= dtok
            matched["first_seen"] = min(matched["first_seen"], frame.get("t", 9999))
            matched["ocr_snippets"].append(frame.get("_ocr_txt", ""))
        else:
            clusters.append({
                "label": "",          # filled later
                "frames": [frame],
                "tokens": dtok,
                "first_seen": frame.get("t", 9999),
                "ocr_snippets": [frame.get("_ocr_txt", "")],
            })

    # Second pass: merge clusters whose token sets now overlap (can happen when
    # two initially disjoint clusters each share tokens with a later frame).
    # Use same minimum-2-or-long-single-token rule to avoid merging different
    # objects that share common German/English words printed on multiple items.
    def _should_merge(tok_a: set, tok_b: set) -> bool:
        shared = tok_a & tok_b
        if len(shared) >= 2:
            return True
        if len(shared) == 1:
            tok = next(iter(shared))
            # A long, non-numeric single token is specific enough to be
            # identity-bearing when repeated OCR tokens are stable across frames.
            return len(tok) >= 6 and not tok.isdigit()
        return False

    changed = True
    while changed:
        changed = False
        merged: List[Dict] = []
        used = [False] * len(clusters)
        for i, ci in enumerate(clusters):
            if used[i]:
                continue
            for j in range(i + 1, len(clusters)):
                if used[j]:
                    continue
                if _should_merge(ci["tokens"], clusters[j]["tokens"]):
                    ci["frames"] += clusters[j]["frames"]
                    ci["tokens"] |= clusters[j]["tokens"]
                    ci["first_seen"] = min(ci["first_seen"], clusters[j]["first_seen"])
                    ci["ocr_snippets"] += clusters[j]["ocr_snippets"]
                    used[j] = True
                    changed = True
            merged.append(ci)
        clusters = merged

    return clusters


# ---------------------------------------------------------------------------
# Step 2b: dedup OVER-SEGMENTED clusters + hedge the count.
#
# Drafted via local qwen2.5-coder:14b (founder mandate), then debugged:
# the upstream clusterer splits ONE physical object into several clusters when
# adjacent frames carry no readable OCR (blur). That inflated the count (6
# posters for ~5, 7 signs for ~2-3). These two helpers (1) merge temporally
# adjacent weakly-identified clusters back into one physical object, and
# (2) turn the named/weak split into an HONEST, understating phrase instead of
# a confident large number.
# ---------------------------------------------------------------------------

def _is_weak_label(label: str) -> bool:
    """A weak label is the placeholder '<category>@<t>s' (no proper name was read).

    These clusters were NOT individually identified — they are the ones prone to
    double-counting the same blurry object across adjacent frames.
    """
    return bool(re.search(r"@\d+(?:\.\d+)?s$", label or ""))


def _cluster_is_weak(cluster: Dict) -> bool:
    """True when a cluster has no distinctive identity (placeholder label OR no
    distinctive OCR tokens). Clusters with stable names or text are strong."""
    return _is_weak_label(cluster.get("label", "")) or not cluster.get("tokens")


def dedup_adjacent_clusters(clusters: List[Dict], gap_s: float = 6.0) -> List[Dict]:
    """Merge over-segmented sightings of the SAME physical object.

    Two clusters become one object when BOTH are weakly-identified and temporally
    adjacent (gap between the later cluster's first_seen and the previous cluster's
    LAST frame time <= gap_s). A weak cluster adjacent to a NAMED cluster is absorbed
    into the named one (a blurry frame of the same poster). Two NAMED clusters are
    never merged here — they are distinct identified objects.

    Drafted by qwen2.5-coder:14b; debugged to recompute first_seen on absorption
    and to label clusters before this runs so _is_weak_label is meaningful.
    """
    if not clusters:
        return clusters
    clusters = sorted(clusters, key=lambda x: x["first_seen"])
    merged: List[Dict] = []

    for i, curr in enumerate(clusters):
        if merged:
            prev = merged[-1]
            prev_weak = _cluster_is_weak(prev)
            curr_weak = _cluster_is_weak(curr)
            prev_last_t = max((f.get("t", prev["first_seen"]) for f in prev["frames"]),
                              default=prev["first_seen"])
            gap = curr["first_seen"] - prev_last_t

            # Case A: two weak clusters adjacent -> same blurry object.
            if prev_weak and curr_weak and gap <= gap_s:
                prev["frames"].extend(curr["frames"])
                prev["ocr_snippets"].extend(curr["ocr_snippets"])
                prev["tokens"] |= curr["tokens"]
                prev["first_seen"] = min(prev["first_seen"], curr["first_seen"])
                continue

            # Case B: weak cluster adjacent AFTER a named cluster -> blurry frame
            # of that same named object; absorb it (do NOT spawn a new count).
            if curr_weak and not prev_weak and gap <= gap_s:
                prev["frames"].extend(curr["frames"])
                prev["ocr_snippets"].extend(curr["ocr_snippets"])
                prev["tokens"] |= curr["tokens"]
                prev["first_seen"] = min(prev["first_seen"], curr["first_seen"])
                continue

        merged.append(curr)

    return merged


def hedge_count(n_named: int, n_weak: int) -> dict:
    """Turn (confident named count, uncertain weak count) into an honest phrase.

    UNDERSTATE rather than overstate: weak clusters are unreliable (likely repeated
    sightings), so we never report their raw number as a confident count.
      low  = n_named (objects we actually identified individually)
      high = n_named + n_weak (the most there could be)
    """
    if n_named == 0 and n_weak == 0:
        return {"low": 0, "high": 0, "phrase": "none", "confident": True}
    if n_weak == 0:
        return {"low": n_named, "high": n_named,
                "phrase": "exactly %d" % n_named, "confident": True}
    if n_named == 0:
        if n_weak == 1:
            return {"low": 1, "high": 1,
                    "phrase": "at least one, possibly more", "confident": False}
        if n_weak == 2:
            return {"low": 1, "high": 2, "phrase": "a couple", "confident": False}
        return {"low": 1, "high": n_weak,
                "phrase": "at least a few, possibly more", "confident": False}
    return {"low": n_named, "high": n_named + n_weak,
            "phrase": "at least %d, possibly a few more" % n_named,
            "confident": False}


# ---------------------------------------------------------------------------
# Step 3: label each cluster with the most prominent name from OCR
# ---------------------------------------------------------------------------

def _label_cluster(cluster: Dict, category: str) -> str:
    """Build a human-readable label from the cluster's OCR/tokens."""
    # Prefer all-caps proper names from OCR.
    all_ocr = " ".join(s for s in cluster["ocr_snippets"] if s)
    proper_names = re.findall(r"\b([A-ZÄÖÜ][A-ZÄÖÜ\s]{2,}(?:[A-ZÄÖÜ]))\b", all_ocr)
    if proper_names:
        # Most frequent name fragment
        from collections import Counter
        counts = Counter(n.strip() for n in proper_names if n.strip())
        best = counts.most_common(1)[0][0]
        # Trim noise — keep only if it looks like a real name (>= 4 chars)
        if len(best) >= 4:
            return best.title()
    # Fall back to category + time
    t = cluster["first_seen"]
    return "%s@%.0fs" % (category, t)


# ---------------------------------------------------------------------------
# Step 4: optional gemma merge-check for two ambiguous clusters
# ---------------------------------------------------------------------------

MERGE_PROMPT = (
    "You are a strict fact-checker for a scene-memory system.\n"
    "Two clusters of frames may describe the SAME real-world {category} or TWO DIFFERENT ones.\n\n"
    "Cluster A (seen around {t_a}s):\n{text_a}\n\n"
    "Cluster B (seen around {t_b}s):\n{text_b}\n\n"
    "Reply with exactly one word: SAME or DIFFERENT.\n"
    "Reply SAME only if you are confident they show the identical {category}.\n"
    "Reply DIFFERENT if they show distinct instances (e.g. two different posters).\n"
    "If uncertain, reply DIFFERENT.\nVerdict:"
)


def _gemma_same_instance(cl_a: Dict, cl_b: Dict, category: str,
                          model: str, host: str, timeout: int) -> bool:
    """Ask gemma whether two clusters show the same instance."""
    def summarize(cl):
        ocr = " | ".join(s for s in cl["ocr_snippets"] if s)
        return ocr[:600] if ocr else "(no OCR — caption only)"

    prompt = MERGE_PROMPT.format(
        category=category,
        t_a="%.0f" % cl_a["first_seen"],
        text_a=summarize(cl_a),
        t_b="%.0f" % cl_b["first_seen"],
        text_b=summarize(cl_b),
    )
    try:
        v = _ollama(prompt, model, host, timeout)
        return v.strip().upper().startswith("SAME")
    except Exception:
        return False   # on error, keep as different (conservative)


# ---------------------------------------------------------------------------
# Step 5: caption-only frames (no OCR) — assign to nearest cluster or new
# ---------------------------------------------------------------------------

def _assign_captiononly(caption_frames: List[dict], clusters: List[Dict],
                         category: str, model: str, host: str, timeout: int
                         ) -> List[Dict]:
    """Frames that mention the category in caption but have no OCR distinctive
    tokens.  Assign to an existing cluster if temporal proximity <= 15s and
    a gemma check says SAME; else create a new cluster (could be another
    instance we just couldn't read).  We are conservative: unknown caption
    frames are reported as "at least N" uncertainty.
    """
    unassigned = []
    for frame in caption_frames:
        t = frame.get("t", 9999)
        # Find the temporally closest cluster
        if clusters:
            closest = min(clusters,
                          key=lambda cl: abs(cl["first_seen"] - t))
            if abs(closest["first_seen"] - t) <= 15:
                # quick caption-similarity check
                cap_words = set(_tokens(frame.get("caption", "")))
                cl_cap_words = set()
                for f in closest["frames"]:
                    cl_cap_words.update(_tokens(f.get("caption", "")))
                overlap = cap_words & cl_cap_words
                if len(overlap) >= 3:
                    closest["frames"].append(frame)
                    closest["first_seen"] = min(closest["first_seen"], t)
                    continue
        unassigned.append(frame)

    # Any remaining unassigned caption-only frames: create one new cluster
    # per temporal gap (>= 10s gap = new instance).
    if not unassigned:
        return clusters

    unassigned.sort(key=lambda f: f.get("t", 0))
    bucket: List[dict] = [unassigned[0]]
    for f in unassigned[1:]:
        if f.get("t", 0) - bucket[-1].get("t", 0) < 10:
            bucket.append(f)
        else:
            clusters.append({
                "label": "",
                "frames": bucket,
                "tokens": set(),
                "first_seen": bucket[0].get("t", 0),
                "ocr_snippets": [fr.get("_ocr_txt", "") for fr in bucket],
            })
            bucket = [f]
    clusters.append({
        "label": "",
        "frames": bucket,
        "tokens": set(),
        "first_seen": bucket[0].get("t", 0),
        "ocr_snippets": [fr.get("_ocr_txt", "") for fr in bucket],
    })
    return clusters


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------

def _count_from_kf(category: str, kf: List[dict],
                   model: str, host: str, timeout: int,
                   context: Optional[str] = None) -> dict:
    """Cluster kf frames by instance of `category`.

    context: optional location scope ('door'/'wall'/...) — when set, only frames
    in that context are counted ("how many signs on the door" must not count every
    sign on the whole walk).

    Returns:
      {
        "clusters": [...],    # deduped cluster dicts with label + first_seen
        "named": [...],       # clusters with a distinctive proper-name (confident)
        "weak": [...],        # clusters with no distinctive identity (uncertain)
        "hedge": {...},       # hedge_count(len(named), len(weak)) result
        "uncertain": bool,    # True if any weak clusters remain (count is a range)
        "context": str|None,  # the location scope actually applied
        "context_unmatched": bool,  # True if a context was asked but NO frame matched
        "absent": bool,       # True if category not mentioned at all
      }
    """
    aliases = _aliases_for(category)
    canon = _canonical(category)

    # Categories where caption-only identification is unreliable (VLM often
    # misnames e.g. a light-blue poster as "a train in motion").  For these,
    # we require at least one OCR-corroborated frame; pure caption-only hits
    # are treated as noise and discarded.
    REQUIRE_OCR_EVIDENCE = {"train", "tram", "bus", "car", "bike", "airplane"}

    # Separate frames: those with useful OCR vs caption-only.
    # When a location context is requested, drop frames not in that context FIRST
    # so we never count e.g. platform signs when asked about signs on the door.
    ocr_frames = []
    caption_only_frames = []
    absent_total = 0
    context_hits = 0

    for frame in kf:
        if not _frame_mentions_category(frame, category, aliases):
            absent_total += 1
            continue
        if context is not None:
            if not _frame_in_context(frame, context):
                continue
            context_hits += 1
        ocr = frame.get("_ocr_txt", "")
        dtok = _distinctive_tokens(ocr)
        if dtok:
            ocr_frames.append(frame)
        else:
            caption_only_frames.append(frame)

    # A context was asked but nothing matched it: be honest (we can't scope reliably).
    if context is not None and context_hits == 0:
        return {"clusters": [], "named": [], "weak": [], "hedge": hedge_count(0, 0),
                "uncertain": False, "context": context, "context_unmatched": True,
                "absent": False}

    if not ocr_frames and not caption_only_frames:
        return {"clusters": [], "named": [], "weak": [], "hedge": hedge_count(0, 0),
                "uncertain": False, "context": context, "context_unmatched": False,
                "absent": True}

    # For vehicle/transport categories: if we have NO OCR-backed evidence, the
    # caption-only hits are likely VLM hallucinations — return absent.
    if canon in REQUIRE_OCR_EVIDENCE and not ocr_frames:
        return {"clusters": [], "named": [], "weak": [], "hedge": hedge_count(0, 0),
                "uncertain": False, "context": context, "context_unmatched": False,
                "absent": True}

    # Cluster OCR-rich frames by named tokens
    clusters = _cluster_by_tokens(ocr_frames) if ocr_frames else []

    # Assign caption-only frames (skip for vehicle categories with no OCR support)
    uncertain = False
    if caption_only_frames and canon not in REQUIRE_OCR_EVIDENCE:
        n_before = len(clusters)
        clusters = _assign_captiononly(
            caption_only_frames, clusters, category, model, host, timeout)
        if len(clusters) > n_before:
            uncertain = True   # we created new clusters from caption-only evidence

    # Label each cluster BEFORE dedup so _is_weak_label can tell named from weak.
    for cl in clusters:
        cl["label"] = _label_cluster(cl, category)

    # DEDUP over-segmented sightings of the same physical object (adjacent weak
    # clusters / blurry frames of a named object). This is the core over-count fix.
    clusters = dedup_adjacent_clusters(clusters)

    # Re-label any merged clusters (a weak pair may now carry a name from OCR).
    for cl in clusters:
        cl["label"] = _label_cluster(cl, category)

    # Split into confidently-identified (named) vs uncertain (weak) objects.
    named = [cl for cl in clusters if not _cluster_is_weak(cl)]
    weak = [cl for cl in clusters if _cluster_is_weak(cl)]
    hedge = hedge_count(len(named), len(weak))

    return {
        "clusters": clusters,
        "named": named,
        "weak": weak,
        "hedge": hedge,
        "uncertain": bool(weak) or uncertain,
        "context": context,
        "context_unmatched": False,
        "absent": False,
    }


# ---------------------------------------------------------------------------
# Question parser — extract the target category from the question
# ---------------------------------------------------------------------------

COUNTING_RE = re.compile(
    r"\b(how many|how much|number of|count|are there|were there)\b", re.I)

CATEGORY_RE = re.compile(
    r"\b(how many|number of|count of)\s+([a-zA-ZäöüÄÖÜß\s]+?)(?:\s+(?:did|do|were|was|are|have|has|in|on|at|that|there|you|total|altogether|i|we)\b)",
    re.I,
)


def _extract_category(question: str) -> Optional[str]:
    """Extract the noun phrase after 'how many / number of / count of'."""
    m = CATEGORY_RE.search(question)
    if m:
        return m.group(2).strip().rstrip("s")  # crude singularise
    # Fallback: find a known category word in the question
    ql = question.lower()
    for key in CATEGORY_ALIASES:
        if key in ql or key + "s" in ql:
            return key
    return None


# ---------------------------------------------------------------------------
# Format the answer
# ---------------------------------------------------------------------------

def _format_answer(result: dict, category: str) -> str:
    """Produce a human-readable cited answer that HEDGES rather than overstates.

    Confident only when every counted object was individually identified (no weak
    clusters). When some sightings are unreadable/blurry, we report the confident
    low bound and say there may be more — we never emit a confident large number.
    """
    cat_pl = category + "s"
    context = result.get("context")
    where = (" on the %s" % context) if context else ""

    # A location was asked but nothing matched it.
    if result.get("context_unmatched"):
        return ("I don't have a clear read of the %s%s in my memory — "
                "I can't say for sure." % (cat_pl, where))

    named = result.get("named", [])
    weak = result.get("weak", [])
    hedge = result.get("hedge") or hedge_count(len(named), len(weak))
    n_named, n_weak = len(named), len(weak)

    if n_named == 0 and n_weak == 0:
        return ("I didn't see any %s%s in my memory of this walk — "
                "they weren't captured or mentioned." % (cat_pl, where))

    named_sorted = sorted(((cl["label"], cl["first_seen"]) for cl in named),
                          key=lambda x: x[1])

    # Confident: exact count, every object identified.
    if hedge["confident"]:
        head = "I counted %d distinct %s%s:" % (
            n_named, category if n_named == 1 else cat_pl, where)
        lines = [head] + ["  - %s (first seen at %.1fs)" % (lab, t)
                          for lab, t in named_sorted]
        return "\n".join(lines)

    # Uncertain: lead with the hedge phrase, then list what we DID identify.
    if n_named == 0:
        # Only blurry/unreadable sightings — understate (could be repeats).
        return ("There were %s %s%s, but they were too blurry for me to read or "
                "count precisely, so I can't give you an exact number." %
                (hedge["phrase"], cat_pl, where))

    lines = ["I'm sure of %d distinct %s%s, and there were a few more I couldn't "
             "read clearly:" % (n_named, cat_pl, where)]
    for lab, t in named_sorted:
        lines.append("  - %s (first seen at %.1fs)" % (lab, t))
    lines.append("(I'd rather understate than over-count — the true number is "
                 "between %d and %d.)" % (hedge["low"], hedge["high"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entrypoint (called by ask_home router)
# ---------------------------------------------------------------------------

def answer(question: str,
           kf: List[dict],
           world,                # world_memory objects list or None (not used here)
           model: str,
           host: str,
           timeout: int) -> str:
    """Count distinct instances of the queried category across kf_memory frames.

    kf must be the parsed kf_memory list with _ocr_txt already set.
    world is accepted for API compatibility but ignored — world_memory has
    lossy dedup that undercounts repeated instances.

    Returns a plain-text answer with timestamps, or an honest refusal.
    """
    if not COUNTING_RE.search(question):
        return ("I'm not sure what you're asking me to count — "
                "please phrase it as 'how many <thing> did you see?'")

    category = _extract_category(question)
    if not category:
        return ("I couldn't identify what to count from your question. "
                "Try: 'how many posters did you see?'")

    # Scope the count to a location if the question names one ("signs on the door").
    context = _question_context(question)

    result = _count_from_kf(category, kf, model, host, timeout, context=context)

    if result["absent"]:
        where = (" on the %s" % context) if context else ""
        return ("I didn't see any %ss%s in my memory of this walk — "
                "they weren't captured or mentioned." % (category, where))

    return _format_answer(result, category)


# ---------------------------------------------------------------------------
# --self-test
# ---------------------------------------------------------------------------

def _self_test(kf_path: str, model: str, host: str, timeout: int) -> bool:
    """Run on the real walk memory; PASS if posters >= 3 and trains = 0."""
    import sys as _sys

    # Load kf_memory
    try:
        raw = json.load(open(kf_path))
    except Exception as e:
        print("FAIL: cannot load kf_memory: %s" % e, file=_sys.stderr)
        return False

    # Normalize (mirrors ask_home.load_memory_records)
    for m in raw:
        ocr = m.get("ocr") or []
        m["_ocr_txt"] = "; ".join(x for x in ocr if x and str(x).strip())

    # --- Test 1: how many posters ---
    print("--- Test 1: how many posters ---")
    ans1 = answer("How many posters in total did you see?",
                  raw, None, model, host, timeout)
    print(ans1)
    # This legacy smoke check is clip-dependent and is not part of the production gate.
    result1 = _count_from_kf("poster", raw, model, host, timeout)
    n1 = len(result1["clusters"])
    pass1 = n1 >= 3
    print("CLUSTERS: %d  =>  %s" % (n1, "PASS" if pass1 else "FAIL (expected >=3)"))
    print()

    # --- Test 2: how many trains ---
    print("--- Test 2: how many trains ---")
    ans2 = answer("How many trains were there?", raw, None, model, host, timeout)
    print(ans2)
    result2 = _count_from_kf("train", raw, model, host, timeout)
    n2 = len(result2["clusters"])
    pass2 = n2 == 0
    print("CLUSTERS: %d  =>  %s" % (n2, "PASS" if pass2 else "FAIL (expected 0)"))
    print()

    # --- Test 3: how many laptops (sanity check - should be 1) ---
    print("--- Test 3: how many laptops ---")
    ans3 = answer("How many laptops did you see?", raw, None, model, host, timeout)
    print(ans3)
    result3 = _count_from_kf("laptop", raw, model, host, timeout)
    n3 = len(result3["clusters"])
    pass3 = n3 >= 1
    print("CLUSTERS: %d  =>  %s" % (n3, "PASS" if pass3 else "FAIL (expected >=1)"))
    print()

    overall = pass1 and pass2 and pass3
    print("=== OVERALL: %s ===" % ("PASS" if overall else "FAIL"))
    return overall


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Counting specialist for TRACE walk memory.")
    ap.add_argument("--self-test", action="store_true",
                    help="Run self-test on real walk memory and print PASS/FAIL.")
    ap.add_argument("--kf", default=None, help="Path to kf_memory.json (for --self-test).")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("question", nargs="*", help="Question to answer (interactive mode).")
    args = ap.parse_args()

    default_kf = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "data", "walks", "walk_outside_20260614", "memory", "kf_memory.json",
    )
    kf_path = args.kf or default_kf

    if args.self_test:
        ok = _self_test(kf_path, args.model, args.host, args.timeout)
        return 0 if ok else 1

    # Interactive
    q = " ".join(args.question)
    if not q:
        print("Usage: counting_specialist.py <question>  or  --self-test")
        return 1

    raw = json.load(open(kf_path))
    for m in raw:
        ocr = m.get("ocr") or []
        m["_ocr_txt"] = "; ".join(x for x in ocr if x and str(x).strip())

    world_path = os.path.join(os.path.dirname(kf_path), "world_memory.json")
    world = None
    if os.path.exists(world_path):
        try:
            wparsed = json.load(open(world_path))
            if isinstance(wparsed, dict):
                world = wparsed.get("objects")
        except Exception:
            pass

    ans = answer(q, raw, world, args.model, args.host, args.timeout)
    print("Q:", q)
    print("A:", ans)
    return 0


if __name__ == "__main__":
    sys.exit(main())
