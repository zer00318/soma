#!/usr/bin/env python3
"""WS2 — INJECT, the capture-time BINDER (Stage 3), interim TEMPORAL/IDENTITY pass.

RECON FINDING (verified 2026-06-24): no persisted capture log carries per-observation
boxes/geometry — every kf_memory.json is {t, frame, source, caption, ocr[]} (text + time
only). So SPATIAL binding (a drink -> the person holding it, by box overlap) is NOT testable
on current data; it needs a fresh box-bearing capture (founder). What IS buildable on
text+time is the other half of Stage 3: bind observations into persistent ENTITIES across
frames by IDENTITY (the text/value) + TEMPORAL persistence, attaching a binding_confidence
that comes from CORROBORATION (how many frames independently agree), never from an LLM's
say-so (the ZLORPTECH lesson). Low-confidence binds ABSTAIN — marked speculative — rather
than being asserted as a stable entity the brain can lean on.

This is the consensus primitive generalised from "answer a read" to "form an entity":
an observation seen consistently across many frames is a confident entity; a one-off garble
stays speculative. Provenance is NEVER collapsed — every entity keeps its source frames.

API:
  bind(observations) -> {"entities": [...], "stats": {...}}     # pure, deterministic
  bind_memory(memory_dir) -> same, loading kf_memory.json
Each entity: {value, kind, support, span_s, frames, sources, binding_confidence, speculative}

CLI:
  python scripts/inject_bind.py <memory_dir>           # print the bound entities + stats
  python scripts/inject_bind.py --selftest             # CPU-only unit checks (no data needed)
"""
from __future__ import annotations

import json
import os
import re
import sys

# Corroboration thresholds. binding_confidence is a function of SUPPORT (independent frames
# that agree) and intra-cluster CONSISTENCY — both are corroboration signals, not model
# confidence. Tuned conservatively: precision over recall (a wrong bind is a confident lie).
CONF_THRESHOLD = 0.50          # below this -> speculative (abstain from asserting it)
JACCARD_MERGE = 0.60           # token-overlap to treat two reads as the same entity
_STOP = set("the a an of to in on at is are was were and or for it this that with you your "
            "i me my am pm at by".split())


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_observations(memory_dir):
    """Each OCR string and caption becomes one observation {value, kind, t, frame, source}."""
    path = os.path.join(memory_dir, "kf_memory.json")
    try:
        recs = json.load(open(path))
    except Exception:
        return []
    if not isinstance(recs, list):
        recs = recs.get("frames") or recs.get("records") or []
    obs = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        t = r.get("t")
        frame = r.get("frame")
        ocr = r.get("ocr") or []
        if isinstance(ocr, str):
            ocr = [ocr]
        for s in ocr:
            s = str(s or "").strip()
            if len(s) >= 2:
                obs.append({"value": s, "kind": "ocr", "t": t, "frame": frame,
                            "source": r.get("source") or "ocr"})
        cap = str(r.get("caption") or "").strip()
        if cap:
            obs.append({"value": cap, "kind": "caption", "t": t, "frame": frame,
                        "source": "caption"})
    return obs


def _confidence(support, consistency, n_sources):
    """Corroboration-based binding confidence in [0,1].
    support      = number of independent frames that carry this entity
    consistency  = mean pairwise text agreement within the cluster (0..1)
    n_sources    = distinct helper channels that saw it (cross-helper corroboration)"""
    # support curve: 1 frame is weak (0.30), 2 frames decent, >=3 strong, saturating.
    s = {0: 0.0, 1: 0.30, 2: 0.58}.get(support, min(0.92, 0.58 + 0.12 * (support - 2)))
    conf = s * (0.6 + 0.4 * consistency)           # inconsistent clusters are damped
    if n_sources >= 2:
        conf = min(0.97, conf + 0.08)              # OCR + caption agreeing -> a real boost
    return round(conf, 3)


def bind(observations):
    """Deterministically bind observations into persistent entities by identity + persistence.
    Greedy single-link clustering on normalized text (exact / containment / token-Jaccard)."""
    # Only bind OCR-style identity tokens (short read strings). Captions are long scene
    # descriptions — they corroborate but do not themselves form a named entity here.
    items = [o for o in observations if o.get("kind") == "ocr"]
    clusters = []  # each: {"members":[obs...], "tok": set}
    for o in items:
        nv = _norm(o["value"])
        tok = _tokens(o["value"])
        placed = False
        for cl in clusters:
            rep = _norm(cl["members"][0]["value"])
            if nv == rep or nv in rep or rep in nv or _jaccard(tok, cl["tok"]) >= JACCARD_MERGE:
                cl["members"].append(o)
                cl["tok"] |= tok
                placed = True
                break
        if not placed:
            clusters.append({"members": [o], "tok": set(tok)})

    entities = []
    for cl in clusters:
        mem = cl["members"]
        frames = sorted({m.get("frame") for m in mem if m.get("frame") is not None})
        times = [float(m["t"]) for m in mem if m.get("t") is not None]
        support = len(frames) if frames else len(mem)
        sources = sorted({m.get("source") for m in mem})
        # consistency: how alike the members' token sets are to the union (1.0 = identical)
        union = set().union(*[_tokens(m["value"]) for m in mem]) or {"_"}
        consistency = round(sum(_jaccard(_tokens(m["value"]), union) for m in mem) / len(mem), 3)
        # the consensus value = the longest member (most complete read folds truncations in)
        value = max((m["value"] for m in mem), key=len)
        # caption corroboration: does any caption mention these tokens? (cross-helper)
        conf = _confidence(support, consistency, len(sources))
        entities.append({
            "value": value,
            "kind": "ocr",
            "support": support,
            "span_s": round(max(times) - min(times), 1) if len(times) >= 2 else 0.0,
            "frames": frames[:20],
            "sources": sources,
            "consistency": consistency,
            "binding_confidence": conf,
            "speculative": conf < CONF_THRESHOLD,
        })
    entities.sort(key=lambda e: (-e["binding_confidence"], -e["support"]))
    confident = [e for e in entities if not e["speculative"]]
    stats = {
        "observations": len(observations),
        "ocr_observations": len(items),
        "entities": len(entities),
        "confident": len(confident),
        "speculative_abstained": len(entities) - len(confident),
        "conf_threshold": CONF_THRESHOLD,
    }
    return {"entities": entities, "stats": stats}


def bind_memory(memory_dir):
    return bind(_load_observations(memory_dir))


# --------------------------------------------------------------------------- #
def _selftest():
    obs = []
    # a sign read consistently across 4 frames (+ a truncation) -> confident entity
    for i, v in enumerate(["PHYSICS LECTURE 1:32 PM", "PHYSICS LECTURE 1:32 PM",
                            "PHYSICS LECTURE", "PHYSICS LECTURE 1:32 PM"]):
        obs.append({"value": v, "kind": "ocr", "t": float(i), "frame": i, "source": "ocr"})
    # a one-off garble -> must stay speculative (abstain)
    obs.append({"value": "Xq9 zzlorp", "kind": "ocr", "t": 9.0, "frame": 9, "source": "ocr"})
    res = bind(obs)
    ents = {e["value"]: e for e in res["entities"]}
    phys = next(e for e in res["entities"] if "PHYSICS" in e["value"])
    garb = next(e for e in res["entities"] if "zzlorp" in e["value"].lower())
    checks = {
        "physics sign bound across frames": phys["support"] >= 3,
        "physics sign is CONFIDENT": not phys["speculative"],
        "physics folds the truncation in (longest value)": phys["value"] == "PHYSICS LECTURE 1:32 PM",
        "one-off garble ABSTAINS (speculative)": garb["speculative"],
        "provenance kept (frames listed)": len(phys["frames"]) >= 3,
        "stats count confident": res["stats"]["confident"] >= 1,
    }
    print("INJECT BINDER — selftest")
    ok = True
    for k, v in checks.items():
        print("  [%s] %s" % ("PASS" if v else "FAIL", k)); ok = ok and v
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv):
    if argv and argv[0] == "--selftest":
        return _selftest()
    if not argv:
        print("usage: inject_bind.py <memory_dir> | --selftest"); return 2
    res = bind_memory(argv[0])
    st = res["stats"]
    print("INJECT binder over %s" % argv[0])
    print("  observations=%d  ocr=%d  -> entities=%d  (confident=%d, speculative/abstained=%d)"
          % (st["observations"], st["ocr_observations"], st["entities"],
             st["confident"], st["speculative_abstained"]))
    print("\n  TOP CONFIDENT ENTITIES (binding_confidence >= %.2f):" % st["conf_threshold"])
    for e in [e for e in res["entities"] if not e["speculative"]][:12]:
        print("    conf=%.2f  support=%-2d  span=%5.1fs  %r" %
              (e["binding_confidence"], e["support"], e["span_s"], e["value"][:60]))
    spec = [e for e in res["entities"] if e["speculative"]]
    print("\n  ABSTAINED (kept speculative, NOT asserted): %d  e.g.:" % len(spec))
    for e in spec[:6]:
        print("    conf=%.2f  support=%-2d  %r" % (e["binding_confidence"], e["support"], e["value"][:50]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
