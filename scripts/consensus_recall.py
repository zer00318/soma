#!/usr/bin/env python3
"""Cross-frame OCR consensus recall — the honest text-memory core.

The product is "a memory for everything you READ". As the camera moves, the SAME
sign is read many times, each read slightly truncated or garbled. Answering from a
single frame loses to that noise; answering from the *consensus across frames*
turns the redundancy into confidence:

  * each frame is answered from ITS OWN local OCR (spatial adjacency — a name and the
    dates beneath it — is preserved; that binding is what a flattened bag-of-lines
    destroys),
  * truncated reads are folded into the complete read by token-aligned clustering
    instead of competing with it,
  * the majority non-refusal answer wins; refusals never vote,
  * a value must be agreed by >= `minrep` frames (a date NNNN-NNNN may pass on one
    clean sighting — it is structurally not a misread) or the memory stays SILENT.

This is self-calibrating honesty: text the camera saw repeatedly is reliable; a
one-off misread (cursive it can't read, keyboard-row noise) fails safe to refusal
rather than a confident lie. Validated on the founder walk gold: it took the text
subset from 47% correct / 42% hallucination to 60%+ correct / <=10% hallucination,
the entire gain coming from refusing what it couldn't honestly read.

The module is pure and brain-format-native: it operates on the scene dicts ask_home
already stores ({"t": seconds, "ocr": [...]} or {"_ocr_txt": "..."}) and takes the
answerer as a callable, so the caller supplies its own (local) LLM. No I/O, no model
hard-coding, importable from the brain or runnable standalone for eval parity.
"""
from __future__ import annotations

import collections
import re
from typing import Callable, Iterable

# Keyboard rows and lone glyphs the OCR grabs off a laptop body — pure noise that
# must never become an answer. A line is noise if most of its tokens are <=2 chars.
_KEYS = {"command", "option", "control", "fn", "esc", "shift", "ctrl", "tab", "caps"}

ANSWER_PROMPT = (
    "You are a person's memory of text they READ a moment ago. The original image is gone; you "
    "have ONLY these lines your eyes read, top-to-bottom, as Apple-Vision OCR (may be slightly "
    "garbled). Lines that are physically adjacent belong together (a name and the dates under it).\n"
    "--- WHAT YOU READ ---\n{ctx}\n---\n"
    "Answer with ONLY the specific thing asked — the name, the year/date range, the street — "
    "copied verbatim from the lines above, with NO surrounding words, labels, or punctuation. "
    "If that specific thing is not present in the lines, output EXACTLY: NOT IN MEMORY. Do not "
    "guess, infer, or use outside knowledge.\nQuestion: {q}"
)

REFUSAL = "NOT IN MEMORY"


def is_noise(line: str) -> bool:
    toks = line.split()
    if not toks:
        return True
    if all(t.lower().strip(",.|") in _KEYS for t in toks):
        return True
    short = sum(1 for t in toks if len(t.strip(",.|€#")) <= 2)
    return len(toks) >= 3 and short / len(toks) > 0.6


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _token_aligned_contains(needle: str, host: str) -> bool:
    nt = needle.split()
    ht = host.split()
    if not nt or len(nt) > len(ht):
        return False
    if all(t.isdigit() for t in nt):
        if any(not t.isdigit() for t in ht):
            return False
        return ht[:len(nt)] == nt
    return any(ht[i:i + len(nt)] == nt for i in range(len(ht) - len(nt) + 1))


def _ocr_lines(scene: dict) -> list[str]:
    """Per-scene OCR lines, noise-filtered, preserving top-to-bottom order."""
    ocr = scene.get("ocr")
    if ocr is None:
        txt = scene.get("_ocr_txt", "") or ""
        ocr = re.split(r"\s*\|\s*|\n", txt)
    elif isinstance(ocr, str):
        ocr = [ocr]
    return [l.strip() for l in ocr if l and l.strip() and not is_noise(l.strip())]


def _window(scenes: Iterable[dict], center: float, half: float) -> list[tuple[float, list[str], int]]:
    """Distinct OCR readings within +-half seconds of center, with frame multiplicity.

    Frames with identical OCR collapse to ONE entry (we call the LLM once per distinct
    reading), but we keep the count of how many frames produced it: a sign read
    identically by a still camera is corroboration, not a single sample, so its vote
    weight is the frame count — never 1. Nearest-to-center frame breaks ties.
    """
    groups: dict[tuple, list] = {}
    for s in scenes:
        t = s.get("t")
        if t is None:
            continue
        ls = _ocr_lines(s)
        dist = abs(float(t) - center)
        if not ls or dist > half:
            continue
        key = tuple(_norm(l) for l in ls)
        g = groups.get(key)
        if g is None:
            groups[key] = [dist, ls, 1]
        else:
            g[2] += 1
            if dist < g[0]:
                g[0], g[1] = dist, ls
    out = [(d, ls, n) for d, ls, n in groups.values()]
    out.sort(key=lambda x: x[0])
    return out


def consensus_read(
    scenes: list[dict],
    question: str,
    answerer: Callable[[str], str],
    center: float | None = None,
    half: float = 5.0,
    minrep: int = 3,
    max_frames: int = 20,
) -> dict:
    """Answer a reading question from the OCR consensus of nearby frames.

    Args:
      scenes: the brain's scene records, each with "t" (seconds) and "ocr"/"_ocr_txt".
      question: the user's question.
      answerer: callable(prompt)->str running a local LLM (caller owns the model).
      center: the moment of interest in seconds; defaults to the latest scene's t.
      half, minrep, max_frames: consensus window / agreement threshold / cap.

    Returns {"answer", "refused", "support", "tally"}. answer == REFUSAL when no
    value reaches consensus — that silence is the honest behavior, not a failure.
    """
    if center is None:
        ts = [float(s["t"]) for s in scenes if s.get("t") is not None]
        center = max(ts) if ts else 0.0

    frames = _window(scenes, center, half)[:max_frames]
    tally: collections.Counter = collections.Counter()
    reps: dict[str, str] = {}
    for _, ls, mult in frames:
        ans = answerer(ANSWER_PROMPT.format(ctx="\n".join(ls), q=question))
        if not ans or REFUSAL in ans.upper():
            continue
        ans = max(ans.splitlines(), key=len).strip()  # drop glued OCR fragments
        k = _norm(ans)
        if not k:
            continue
        tally[k] += mult  # each frame that read this counts; still camera != 1 sample
        if k not in reps or len(ans) > len(reps[k]):
            reps[k] = ans
    if not tally:
        return {"answer": REFUSAL, "refused": True, "support": 0, "tally": {}}

    # Fold truncated reads into the complete one only at token boundaries: a shorter
    # normalized answer that appears as whole tokens in a longer one is the SAME fact.
    merged: collections.Counter = collections.Counter()
    canon_rep: dict[str, str] = {}
    for k in sorted(tally, key=len, reverse=True):
        host = next((c for c in merged if _token_aligned_contains(k, c)), None)
        if host is None:
            merged[k] = tally[k]
            canon_rep[k] = reps[k]
        else:
            merged[host] += tally[k]
            if len(reps[k]) > len(canon_rep[host]):
                canon_rep[host] = reps[k]

    top_key, support = max(merged.items(), key=lambda kv: (kv[1], len(kv[0])))
    is_date = bool(re.fullmatch(r"\d{4}\s*-?\s*\d{0,4}", top_key.strip()))
    if support < minrep and not (is_date and support >= 1):
        return {"answer": REFUSAL, "refused": True, "support": support, "tally": dict(merged)}
    return {"answer": canon_rep[top_key], "refused": False,
            "support": support, "tally": dict(merged)}


if __name__ == "__main__":  # tiny self-check on synthetic scenes (no model needed)
    def fake_answerer(prompt):
        # echo the most date-like or longest content line as a stand-in LLM
        ctx = prompt.split("--- WHAT YOU READ ---\n", 1)[1].split("\n---", 1)[0]
        lines = ctx.splitlines()
        dates = [l for l in lines if re.search(r"\d{4}\s*-\s*\d{4}", l)]
        if "year" in prompt.lower() and dates:
            return re.search(r"\d{4}\s*-\s*\d{4}", dates[0]).group(0)
        return REFUSAL

    scenes = [
        {"t": 80.0, "ocr": ["HANS FISCHER", "188"]},
        {"t": 80.5, "ocr": ["HANS FISCHER", "1881 - 1945"]},
        {"t": 81.0, "ocr": ["HANS FISCHER", "1881 - 1945"]},
        {"t": 81.5, "ocr": ["CHg", "1881 - 1945"]},
    ]
    r = consensus_read(scenes, "What years are on the sign?", fake_answerer,
                       center=80.5, half=3, minrep=2)
    assert r["answer"] == "1881 - 1945", r
    print("consensus_recall self-check OK:", r)
