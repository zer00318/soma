#!/usr/bin/env python3
"""Sprint 1 / increment 1 — STRUCTURAL confidence by corroboration (no prompt rules).

A fact seen across many frames / multiple channels is strong; a fact resting on ONE
blurry caption is weak (the walk's phantom "train", a one-frame bag colour). This scores
that structurally: term -> {frames it appears in, channels, confidence 0..1}. The brain
can then prefer high-confidence facts and refuse on low ones — deterministic, generalizes
across clips, and accrues online as frames arrive (live-friendly).

This is provenance + confidence, the first half of the structural brain (the entity graph
is increment 2). It does NOT call an LLM.

CLI:
  python scripts/evidence_confidence.py <memory_dir>            # weakest (phantom-risk) terms
  python scripts/evidence_confidence.py <memory_dir> "a train was in the station"  # score a claim
"""
from __future__ import annotations
import json, os, re, sys

STOP = set("the a an and or of to in on at is was were are be been with for from this that "
           "it its as by image scene photo picture shows showing visible appears there here "
           "left right front back side near next other another some several many few small "
           "large background foreground colour color description layout one two object objects "
           "i you my your me we they he she his her t s read seen looking look".split())
# generic visual genre words that are NOT discriminating facts
GENERIC = set("poster sign signs board panel wall floor room table person people frame "
              "text word words label picture light dark white black gray grey".split())


def _toks(s):
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) > 2 and w not in STOP]


def load_observations(mdir):
    """(t, channel, text) tuples from every text channel — never raw media."""
    obs = []

    def _j(name):
        p = os.path.join(mdir, name)
        try:
            with open(p) as source:
                return json.load(source)
        except Exception:
            return None

    def _jsonl(name):
        rows = []
        p = os.path.join(mdir, name)
        try:
            with open(p) as source:
                for ln in source:
                    ln = ln.strip()
                    if ln:
                        rows.append(json.loads(ln))
        except Exception:
            pass
        return rows

    kf = _j("kf_memory.json")
    if not isinstance(kf, list):
        kf = _jsonl("kf_memory.json") or _jsonl("kf_memory.json.ckpt.ndjson")
    for r in kf or []:
        t = r.get("t")
        cap = r.get("caption") or r.get("description") or ""
        # Channel reliability: a structured object DETECTOR hit (YOLO / native
        # detector) is an INDEPENDENT, more-reliable signal than a free-form VLM
        # caption — so a thing the detector saw AND the caption described is
        # corroborated across channels (real), not a single-channel phantom. An
        # explicit per-record "channel" wins; else detector sources map to "world".
        ch = r.get("channel")
        if not ch:
            src = str(r.get("source") or "").lower()
            if "speech" in src or "asr" in src:
                ch = "speech"
            elif "ocr" in src:
                ch = "ocr"
            elif "detector" in src or "yolo" in src or "vision" in src or "classif" in src:
                ch = "world"   # structured on-device detector (Apple Vision / YOLO)
            else:
                ch = "caption"  # free-form VLM caption (fastvlm_*) or legacy sourceless data
        obs.append((t, ch, cap))
        ocr = r.get("ocr") or r.get("_ocr_txt") or []
        obs.append((t, "ocr", " ".join(ocr) if isinstance(ocr, list) else str(ocr)))
    sm = _j("screen_memory.json") or []
    for r in (sm if isinstance(sm, list) else []):
        obs.append((r.get("t"), "screen", r.get("screen_ocr_txt") or
                    " ".join(r.get("screen_ocr") or [])))
    asr = _j("asr.json") or {}
    for s in asr.get("segments", []):
        obs.append((s.get("start"), "speech", s.get("text") or ""))
    return [(t, ch, tx) for (t, ch, tx) in obs if (tx or "").strip()]


def build_support(observations):
    """term -> {frames:set(t), channels:set(ch)}; corroboration is the signal."""
    sup = {}
    for t, ch, tx in observations:
        for w in set(_toks(tx)):
            d = sup.setdefault(w, {"frames": set(), "channels": set()})
            d["frames"].add(round(t, 1) if isinstance(t, (int, float)) else t)
            d["channels"].add(ch)
    return sup


# Confidence is driven by CHANNEL RELIABILITY, not raw frequency. OCR/ASR/screen are
# verbatim reads (high precision); the 4-bit caption model hallucinates (a phantom "train"
# repeats across many frames — frequency there is NOT truth). Lesson from the data 2026-06-18:
# "train" (caption, 31 frames) must rank BELOW "Joe" (ASR, 1 segment, the real answer).
CHANNEL_REL = {"speech": 0.92, "ocr": 0.90, "screen": 0.88, "world": 0.60, "caption": 0.40}


def term_confidence(d):
    """0..1: the most reliable channel that carries this term, boosted when ≥2 channels agree
    (cross-channel corroboration, e.g. a name in BOTH caption and OCR). Frequency within the
    SAME unreliable channel does NOT raise confidence — that's how a phantom repeats."""
    chans = d["channels"]
    if not chans:
        return 0.0
    base = max(CHANNEL_REL.get(c, 0.40) for c in chans)
    if len(chans) >= 2:
        base = min(1.0, base + 0.20)  # corroborated across independent channels
    return round(base, 3)


def presence_confidence(noun, sup):
    """How confident we are a (possibly GENERIC) presence noun was really there.

    score_claim() strips generic nouns (people/person/sign/car) as non-distinctive,
    returning 0.0 — correct for "what is the distinctive answer", WRONG for "is this
    thing grounded". A noun directly attested in a reliable channel (a detector's
    'world' hit, OCR, speech) IS grounded even when generic; a caption-only mention
    stays low. Used by the phantom-presence floor so 'I saw people' passes when the
    on-device detector saw them, but a single VLM caption phantom does not."""
    conf = score_claim(noun, sup).get("confidence", 0.0)
    key = (noun or "").lower()
    if key in sup:
        conf = max(conf, term_confidence(sup[key]))
    return conf


def score_claim(claim, sup):
    """A claim's confidence = the confidence of its most DISTINCTIVE content token (the rarest
    = the one that actually carries the claim's specificity), not the weakest irrelevant word.
    'my name is Joe' -> 'joe' (the answer); 'a train in the station' -> 'train'."""
    toks = [w for w in set(_toks(claim)) if w not in GENERIC]
    per = {w: (term_confidence(sup[w]) if w in sup else 0.0) for w in toks}
    if not per:
        return {"confidence": 0.0, "key": None, "per_token": {}}
    # distinctive = fewest frames among tokens we actually have evidence for
    have = [w for w in toks if w in sup]
    # distinctive = rarest token; tie-break toward the more reliable one (the proper-noun
    # answer 'joe' beats the common word 'name' when both appear once).
    key = min(have, key=lambda w: (len(sup[w]["frames"]), -per[w])) if have else min(per, key=per.get)
    return {"confidence": per[key], "key": key, "per_token": per}


def main(argv):
    if not argv:
        print("usage: evidence_confidence.py <memory_dir> [\"claim to score\"]"); return 2
    mdir = argv[0]
    obs = load_observations(mdir)
    sup = build_support(obs)
    print("loaded %d observations, %d distinct content terms" % (len(obs), len(sup)))
    if len(argv) > 1:
        r = score_claim(argv[1], sup)
        print("\nclaim: %s" % argv[1])
        print("confidence: %.3f  (key token: %r)" % (r["confidence"], r["key"]))
        for w, c in sorted(r["per_token"].items(), key=lambda x: x[1]):
            d = sup.get(w, {"frames": set(), "channels": set()})
            print("   %-16s conf=%.3f  frames=%d channels=%s" %
                  (w, c, len(d["frames"]), sorted(d["channels"])))
        return 0
    # default: the weakest (phantom-risk) content terms vs the strongest
    scored = [(term_confidence(d), w, len(d["frames"]), sorted(d["channels"]))
              for w, d in sup.items()]
    scored.sort()
    print("\nWEAKEST 15 terms (1-frame phantom risk — these should NOT anchor a confident answer):")
    for c, w, f, ch in scored[:15]:
        print("   %-16s conf=%.3f frames=%d %s" % (w, c, f, ch))
    print("\nSTRONGEST 12 terms (well-corroborated — safe to assert):")
    for c, w, f, ch in scored[-12:][::-1]:
        print("   %-16s conf=%.3f frames=%d %s" % (w, c, f, ch))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
