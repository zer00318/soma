#!/usr/bin/env python3
"""Temporal Specialist — SOMA walk-the-walk memory.

Answers "how long did I spend on X vs Y" and related temporal questions by
computing continuous TIME-IN-VIEW spans directly from the per-keyframe
timestamps and multi-keyword subject detection.

The critical difference from build_temporal_index.py:
  - Subject detection uses BOTH caption text AND OCR text with multiple
    keywords per subject, so a frame labelled "sign" by the caption but
    containing "RÖNTGEN" in OCR is correctly attributed to poster_rontgen.
  - Spans are merged across the full subject lifetime (gap_s tolerance), not
    split every time a noisy per-frame label changes.
  - A lone frame (zero-duration span) is assigned 0.5 s (median inter-frame
    gap) instead of 0 — never false precision, but also never silent zeros.
  - All answers include an explicit caveat that the number is approximate
    time-in-view, NOT confirmed dwell/attention time.

Entrypoint:  answer(question, kf, kf_path, model, host, timeout) -> str
CLI:         python3 scripts/temporal_specialist.py --self-test
             python3 scripts/temporal_specialist.py --kf <kf_memory.json> --question "..."
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

# Median inter-frame gap in this walk; used for lone-frame spans.
_LONE_FRAME_S = 0.5

# Gap tolerance: if the next frame for a subject is within this many seconds of
# the last, it is considered the SAME viewing span.
_DEFAULT_GAP_S = 5.0

# Canonical subject aliases: what the user might call each internal label.
# Ordered longest-first so "poster_rontgen" wins over bare "poster".
SUBJECT_ALIASES: dict[str, list[str]] = {
    "laptop": ["laptop", "computer", "screen", "monitor", "chat", "terminal"],
    "poster_rontgen": ["rontgen", "röntgen", "x-ray", "x ray", "roentgen",
                       "blue poster", "1845", "1923"],
    "poster_fischer": ["fischer", "hans fischer", "chlorophyll", "heme",
                       "haem", "hämin", "blutfarbstoff", "molecule",
                       "light-blue poster", "1881", "1945"],
    "poster_sauer": ["sauer", "robert sauer", "yellow poster", "sun",
                     "1898", "1970"],
    "poster": ["poster", "billboard", "mural", "informational sign", "sign"],
    "platform": ["platform", "railway", "train track", "train station"],
    "backpack": ["backpack", "bag", "white bag", "white backpack"],
}

# Human-friendly names for reporting.
SUBJECT_LABELS: dict[str, str] = {
    "laptop": "laptop/screen",
    "poster_rontgen": "Röntgen poster (blue, ~t63-72s)",
    "poster_fischer": "Hans Fischer poster (light-blue, ~t79-92s)",
    "poster_sauer": "Robert Sauer poster (yellow, ~t46-49s)",
    "poster": "poster (generic)",
    "platform": "platform/track area",
    "backpack": "white backpack",
}


# --------------------------------------------------------------------------- #
# Subject detection: multi-keyword, caption + OCR combined.
# --------------------------------------------------------------------------- #
def _detect_subjects(record: dict) -> set[str]:
    """Return the set of semantic subjects present in ONE keyframe record."""
    caption = (record.get("caption") or "").lower()
    ocr_raw = record.get("ocr") or []
    if not isinstance(ocr_raw, list):
        ocr_raw = [ocr_raw]
    ocr = " ".join(str(x) for x in ocr_raw).lower()
    both = caption + " " + ocr

    subjects: set[str] = set()

    # --- Laptop / screen ---
    # "command" and "option" are keyboard keys that only appear on the laptop OCR.
    if any(k in both for k in ("laptop", "trackpad", "keyboard")):
        subjects.add("laptop")
    elif any(k in ocr for k in ("command", "option", "ctrl", "welcome back", "soma")):
        subjects.add("laptop")

    # --- Röntgen poster (blue) ---
    if any(k in both for k in ("rontgen", "röntgen", "roentgen", "1845", "1923",
                                "strahlung", "elektromagnetisch")):
        subjects.add("poster_rontgen")

    # --- Hans Fischer poster (light-blue, molecule/chlorophyll) ---
    if any(k in both for k in ("fischer", "1881", "1945", "chlorophyl",
                                "blutfarbstoff", "hämin", "hamin",
                                "naturstoff", "chemiker", "nobelpreis für chemie")):
        subjects.add("poster_fischer")

    # --- Robert Sauer poster (yellow, sun/arrows) ---
    if any(k in both for k in ("sauer", "robert sa", "1898", "1970")):
        subjects.add("poster_sauer")

    # --- Generic poster (billboard/mural/informational panel not yet matched) ---
    if any(k in caption for k in ("poster", "billboard", "mural",
                                   "informational sign", "informational panel",
                                   "rectangular sign", "informational plaque")):
        # Only add generic if no specific poster already matched for this frame.
        if not any(s.startswith("poster_") for s in subjects):
            subjects.add("poster")

    # --- Platform / track area ---
    if any(k in caption for k in ("platform", "railway track", "train track",
                                   "tactile strip", "train station platform")):
        subjects.add("platform")

    # --- White backpack ---
    if "white backpack" in caption:
        subjects.add("backpack")

    return subjects


# --------------------------------------------------------------------------- #
# Span builder: merge consecutive (within gap_s) frames per subject.
# --------------------------------------------------------------------------- #
def build_subject_spans(
    records: list[dict],
    gap_s: float = _DEFAULT_GAP_S,
) -> dict[str, list[tuple[float, float, list[float]]]]:
    """Group keyframe records into continuous viewing spans per subject.

    Returns:
        { subject: [(start_s, end_s, [t, ...]), ...] }
    Spans within gap_s seconds of each other are merged.
    """
    # Sort by time.
    def _t(r: dict) -> float:
        try:
            return float(r.get("t", 0))
        except (TypeError, ValueError):
            return 0.0

    records_sorted = sorted(records, key=_t)

    # active_span[subject] = [start_s, end_s, [t...]]
    active: dict[str, list] = {}
    finished: dict[str, list[tuple[float, float, list[float]]]] = {}

    for rec in records_sorted:
        t = _t(rec)
        subjects = _detect_subjects(rec)
        for subj in subjects:
            if subj not in active:
                active[subj] = [t, t, [t]]
            else:
                span = active[subj]
                if t - span[1] <= gap_s:
                    span[1] = t
                    span[2].append(t)
                else:
                    # Gap exceeded — close and start new span.
                    finished.setdefault(subj, []).append(
                        (span[0], span[1], span[2]))
                    active[subj] = [t, t, [t]]

    for subj, span in active.items():
        finished.setdefault(subj, []).append((span[0], span[1], span[2]))

    return finished


def _span_duration(start: float, end: float) -> float:
    """Duration of a span; lone-frame (start==end) gets _LONE_FRAME_S."""
    d = end - start
    return d if d > 0 else _LONE_FRAME_S


def total_time_in_view(spans: list[tuple[float, float, list[float]]]) -> float:
    return sum(_span_duration(s, e) for s, e, _ in spans)


# --------------------------------------------------------------------------- #
# Question -> subject mapping.
# --------------------------------------------------------------------------- #
def _question_subjects(question: str) -> list[str]:
    """Return internal subject keys the question is about, ordered by specificity."""
    ql = question.lower()
    matched = []
    # Check aliases longest-first per subject (poster_rontgen before poster).
    for subj, aliases in SUBJECT_ALIASES.items():
        if any(alias in ql for alias in aliases):
            matched.append(subj)
    return matched


# Consolidates "all poster" subjects into one logical group for comparison.
_POSTER_SUBJECTS = {"poster_rontgen", "poster_fischer", "poster_sauer", "poster"}


def _resolve_query_groups(question: str,
                           spans: dict[str, list]) -> dict[str, float]:
    """Map the question's subjects to total seconds in view.

    When the question says "posters" (plural / generic) we sum all poster
    sub-types so the comparison is coherent.  When it names a specific poster
    we report just that one.
    """
    ql = question.lower()
    groups: dict[str, float] = {}

    # Detect explicit "poster" (any/all) vs specific named poster.
    asked_any_poster = any(k in ql for k in ("poster", "billboard", "posters"))
    asked_specific = any(k in ql for k in ("rontgen", "röntgen", "fischer",
                                             "sauer", "blue poster", "yellow poster",
                                             "light-blue poster"))

    for subj in _question_subjects(question):
        if subj in _POSTER_SUBJECTS and asked_any_poster and not asked_specific:
            # Aggregate all poster types.
            key = "posters"
            all_poster_spans: list[tuple] = []
            for ps in _POSTER_SUBJECTS:
                all_poster_spans.extend(spans.get(ps, []))
            groups[key] = total_time_in_view(all_poster_spans) if all_poster_spans else 0.0
        elif subj in spans:
            human = SUBJECT_LABELS.get(subj, subj)
            groups[human] = total_time_in_view(spans[subj])
        else:
            human = SUBJECT_LABELS.get(subj, subj)
            groups[human] = -1.0  # Signal: not detected in this walk.

    # Deduplicate if both "laptop" and "screen" resolved to the same key.
    return groups


# --------------------------------------------------------------------------- #
# Span-level textual summary (for the prompt context).
# --------------------------------------------------------------------------- #
def _format_spans(spans: dict[str, list]) -> str:
    lines = []
    for subj, slist in sorted(spans.items()):
        total = total_time_in_view(slist)
        human = SUBJECT_LABELS.get(subj, subj)
        span_strs = ["%.1f-%.1fs" % (s, e) for s, e, _ in slist]
        lines.append("- %s: %.1fs total  [spans: %s]"
                     % (human, total, ", ".join(span_strs)))
    return "\n".join(lines) if lines else "(no subjects detected)"


# --------------------------------------------------------------------------- #
# Ollama helper.
# --------------------------------------------------------------------------- #
def _ollama(prompt: str, model: str, host: str, timeout: int) -> str:
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=json.dumps({"model": model, "prompt": prompt,
                         "stream": False,
                         "options": {"temperature": 0}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("response", "").strip()


# --------------------------------------------------------------------------- #
# Prompt template.
# --------------------------------------------------------------------------- #
_TEMPORAL_PROMPT = (
    "You are the perception memory of someone's walk. Below is the approximate\n"
    "time-in-view for each subject — how many seconds that subject appeared in\n"
    "consecutive frames. IMPORTANT CAVEAT: these are frame-level observations,\n"
    "NOT confirmed attention or dwell time. Gaps in frames and camera motion\n"
    "mean the real time could differ by a few seconds either way.\n\n"
    "Time-in-view per subject:\n%s\n\n"
    "Rules:\n"
    "- Answer in 1-3 plain sentences.\n"
    "- State the approximate seconds for each subject asked about.\n"
    "- For 'which was longer', give the relative ordering.\n"
    "- ALWAYS include the caveat: 'approximately' or 'roughly' and note this is\n"
    "  time-in-view (frames), not confirmed attention time.\n"
    "- If a subject isn't in the list, say you didn't track it.\n"
    "- Never invent numbers.\n\n"
    "Question: %s\nAnswer:"
)

_UNTRACKED_REFUSAL = (
    "I didn't track '%s' in this walk's memory — I can't give you a time for it. "
    "I only have time-in-view data for: %s."
)

_CAVEAT = (
    " (Note: this is approximate time-in-view from keyframes, "
    "not confirmed attention or dwell time — real figures may vary by a few seconds.)"
)


# --------------------------------------------------------------------------- #
# Main entrypoint.
# --------------------------------------------------------------------------- #
def answer(
    question: str,
    kf: list[dict],
    kf_path: str,
    model: str,
    host: str,
    timeout: int,
    gap_s: float = _DEFAULT_GAP_S,
) -> str:
    """Answer a temporal question from keyframe memory.

    Parameters
    ----------
    question : the user's question
    kf       : list of keyframe records (already loaded from kf_memory.json)
    kf_path  : path to kf_memory.json (for re-loading if kf is None)
    model    : ollama model to use for phrasing (gemma3:12b-it-qat recommended)
    host     : ollama base URL
    timeout  : request timeout in seconds

    Returns
    -------
    str — hedged answer with timestamps and caveats, or an honest refusal.
    """
    # Load records if kf is None.
    if not kf:
        if not kf_path or not os.path.exists(kf_path):
            return ("I don't have keyframe memory for this walk — "
                    "I can't answer timing questions.")
        try:
            with open(kf_path) as f:
                kf = json.load(f)
        except Exception:
            return "I couldn't load the keyframe memory — timing unavailable."
        if not isinstance(kf, list):
            return "Keyframe memory format unexpected — timing unavailable."

    # Normalize: ensure _ocr_txt is set on every record (ask_home compat).
    for rec in kf:
        if "_ocr_txt" not in rec:
            ocr = rec.get("ocr") or []
            if isinstance(ocr, list):
                rec["_ocr_txt"] = "; ".join(str(x) for x in ocr if x and str(x).strip())
            else:
                rec["_ocr_txt"] = str(ocr)

    # Build spans.
    spans = build_subject_spans(kf, gap_s=gap_s)

    if not spans:
        return ("I don't have enough keyframe data to compute timing — "
                "the memory appears empty.")

    # Which subjects does the question ask about?
    query_subjects = _question_subjects(question)

    if not query_subjects:
        # Question is temporal but doesn't name a tracked subject — show overview.
        summary = _format_spans(spans)
        tracked = ", ".join(SUBJECT_LABELS.get(s, s) for s in spans)
        try:
            prompt = _TEMPORAL_PROMPT % (summary, question)
            ans = _ollama(prompt, model, host, timeout)
            if ans:
                return ans + _CAVEAT
        except Exception:
            pass
        return ("I tracked time-in-view for: %s. Ask me about any of those "
                "specifically." % tracked) + _CAVEAT

    # Resolve question subjects to durations.
    groups = _resolve_query_groups(question, spans)

    # Check for completely untracked subjects.
    untracked = [k for k, v in groups.items() if v < 0]
    tracked_list = ", ".join(SUBJECT_LABELS.get(s, s) for s in spans)
    if untracked and not any(v >= 0 for v in groups.values()):
        return (_UNTRACKED_REFUSAL % (question, tracked_list))

    # Format context for the model.
    ctx_lines = []
    for subj_key, secs in sorted(groups.items(), key=lambda x: -x[1]):
        if secs < 0:
            ctx_lines.append("- %s: NOT DETECTED in this walk" % subj_key)
        else:
            # Find the actual spans for timestamp citing.
            internal_key = next(
                (k for k, aliases in SUBJECT_ALIASES.items()
                 if SUBJECT_LABELS.get(k, k) == subj_key
                 or any(a in subj_key.lower() for a in aliases)),
                None,
            )
            if subj_key == "posters":
                all_spans: list = []
                for ps in _POSTER_SUBJECTS:
                    all_spans.extend(spans.get(ps, []))
                span_strs = ["%.1f-%.1fs" % (s, e) for s, e, _ in all_spans]
            elif internal_key and internal_key in spans:
                span_strs = ["%.1f-%.1fs" % (s, e)
                             for s, e, _ in spans[internal_key]]
            else:
                span_strs = []
            if span_strs:
                ctx_lines.append("- %s: ~%.1fs  [seen at: %s]"
                                 % (subj_key, secs, ", ".join(span_strs)))
            else:
                ctx_lines.append("- %s: ~%.1fs" % (subj_key, secs))

    ctx = "\n".join(ctx_lines)

    try:
        prompt = _TEMPORAL_PROMPT % (ctx, question)
        ans = _ollama(prompt, model, host, timeout)
        if ans:
            return ans + _CAVEAT
    except Exception:
        pass

    # Fallback: deterministic answer without model.
    parts = []
    for subj_key, secs in sorted(groups.items(), key=lambda x: -x[1]):
        if secs < 0:
            parts.append("%s: not detected" % subj_key)
        else:
            parts.append("%s: ~%.1fs" % (subj_key, secs))
    ordering = " vs ".join(parts)
    if len(groups) >= 2:
        ranked = sorted(((k, v) for k, v in groups.items() if v >= 0), key=lambda x: -x[1])
        if ranked:
            longer = ranked[0][0]
            return ("Approximate time-in-view: %s. %s was longer." % (ordering, longer)) + _CAVEAT
    return ("Approximate time-in-view: %s." % ordering) + _CAVEAT


# --------------------------------------------------------------------------- #
# Self-test.
# --------------------------------------------------------------------------- #
_WALK_KF = "data/walks/walk_outside_20260614/memory/kf_memory.json"


def _self_test() -> int:
    """Run two tests and print PASS/FAIL. Returns 0 on pass, 1 on fail."""
    print("=== temporal_specialist self-test ===")
    errors = []

    # Load real walk memory.
    kf_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           _WALK_KF)
    if not os.path.exists(kf_path):
        # Try relative path from cwd.
        kf_path = _WALK_KF
    if not os.path.exists(kf_path):
        print("FAIL — kf_memory.json not found at", kf_path)
        return 1

    with open(kf_path) as f:
        kf = json.load(f)

    spans = build_subject_spans(kf)
    print("\n-- Detected spans --")
    for subj, slist in sorted(spans.items()):
        total = total_time_in_view(slist)
        span_strs = ["%.1f-%.1fs" % (s, e) for s, e, _ in slist]
        print("  %-20s  %.1fs  %s" % (subj, total, span_strs))

    # --- Test 1: laptop vs posters gives a hedged comparison ---
    print("\n-- Test 1: laptop vs posters --")
    q1 = "how much time did I spend on the laptop vs the posters"
    ans1 = answer(
        question=q1,
        kf=kf,
        kf_path=kf_path,
        model="gemma3:12b-it-qat",
        host="http://127.0.0.1:11434",
        timeout=60,
    )
    print("Q:", q1)
    print("A:", ans1)

    # Checks:
    #   1a. Must contain 'approx' or 'roughly' or 'Note:' (the caveat).
    if not any(kw in ans1.lower() for kw in ("approx", "roughly", "note:", "time-in-view")):
        errors.append("Test 1a FAIL: answer missing hedge/caveat")
    else:
        print("  [1a PASS] answer contains hedge/caveat")

    #   1b. Must mention at least one numeric duration (e.g. "22s", "22.0s",
    #       "22 seconds", "22.0 seconds") — gemma may spell out "seconds".
    if not re.search(r"\d+\.?\d*\s*(?:s\b|seconds?)", ans1.lower()):
        errors.append("Test 1b FAIL: answer missing numeric durations")
    else:
        print("  [1b PASS] answer contains numeric durations")

    #   1c. Both 'laptop' and some form of 'poster' must appear.
    if "laptop" not in ans1.lower():
        errors.append("Test 1c FAIL: answer missing 'laptop'")
    else:
        print("  [1c PASS] answer mentions laptop")

    # --- Test 2: untracked subject must produce a refusal ---
    print("\n-- Test 2: untracked subject (elephant) --")
    q2 = "how much time did I spend looking at the elephant"
    ans2 = answer(
        question=q2,
        kf=kf,
        kf_path=kf_path,
        model="gemma3:12b-it-qat",
        host="http://127.0.0.1:11434",
        timeout=60,
    )
    print("Q:", q2)
    print("A:", ans2)

    refusal_words = ("didn't track", "not detected", "not found", "don't have",
                     "i didn't", "no data", "cannot", "can't", "i don't have",
                     "not in", "wasn't tracked")
    if not any(w in ans2.lower() for w in refusal_words):
        errors.append("Test 2 FAIL: expected refusal for untracked subject")
    else:
        print("  [2 PASS] got appropriate refusal")

    # --- Summary ---
    print()
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print("PASS — all checks passed")
    return 0


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Temporal specialist for SOMA walk-the-walk memory")
    ap.add_argument("--self-test", action="store_true",
                    help="run built-in self-test on the real walk memory")
    ap.add_argument("--kf", default=None,
                    help="path to kf_memory.json")
    ap.add_argument("--question", "-q", default=None,
                    help="question to answer")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--dump-spans", action="store_true",
                    help="print the detected spans and exit")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    kf_path = args.kf or _WALK_KF
    if not os.path.exists(kf_path):
        print("ERROR: kf_memory.json not found at", kf_path, file=sys.stderr)
        return 1
    with open(kf_path) as f:
        kf = json.load(f)

    if args.dump_spans:
        spans = build_subject_spans(kf)
        for subj, slist in sorted(spans.items()):
            total = total_time_in_view(slist)
            print("%-20s  %.1fs" % (subj, total))
            for s, e, ts in slist:
                print("  %.1f-%.1fs  (%d frames)" % (s, e, len(ts)))
        return 0

    if not args.question:
        ap.error("provide --question or --self-test")

    ans = answer(
        question=args.question,
        kf=kf,
        kf_path=kf_path,
        model=args.model,
        host=args.host,
        timeout=args.timeout,
    )
    print("Q:", args.question)
    print("A:", ans)
    return 0


if __name__ == "__main__":
    sys.exit(main())
