#!/usr/bin/env python3
"""Semantic retrieval over keyframe text — the memory-finder for ask_home.

The naive IDF token-overlap retriever could not find answers the perception had
already read: "molecule" (question) never matched "molecular" (caption) or
"Molekül"/"Chlorophyll" (German OCR), so the Hans Fischer poster was in memory but
unreachable. A multilingual sentence embedder (bge-m3 via ollama) maps the question
and each frame's text into the same vector space, so "what was the molecule" lands
next to a German chlorophyll plaque regardless of language or word form.

Embeddings are computed once per memory and cached on disk next to it, so re-scores
are instant. Everything degrades gracefully: any failure returns None and ask_home
falls back to the IDF retriever — semantic search lifts recall, it never blocks an
answer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request

# ollama /api/embed crashes (GGML_ASSERT) on this macOS-13/M2 build, so embeddings run
# LOCALLY via sentence-transformers (still fully on-device, no cloud). Multilingual so an
# English question matches German OCR (molecule<->Molekül, crowded<->leer/empty platform).
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_ST_MODEL = None


def frame_text(m):
    """The text we embed for a frame: caption + the verbatim read text. Both matter —
    captions are English ('molecular structure diagram'), OCR is verbatim/multilingual
    ('Molekül', 'HANS FISCHER'); together they make a frame findable either way."""
    cap = m.get("caption", "") or m.get("description", "")
    ocr = m.get("_ocr_txt", "")
    if not ocr:
        o = m.get("ocr") or []
        ocr = "; ".join(x for x in o if x and str(x).strip()) if isinstance(o, list) else str(o)
    return (cap + ("  TEXT: " + ocr if ocr else "")).strip()


def _get_model(model=EMBED_MODEL):
    """Lazy-load the local embedder once per process (first call ~few s)."""
    global _ST_MODEL
    if _ST_MODEL is None:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL = SentenceTransformer(model)
    return _ST_MODEL


def embed_texts(texts, host=None, model=EMBED_MODEL, timeout=600):
    """Batch-embed a list of strings with a LOCAL sentence-transformers model. `host`/
    `timeout` are kept for call-site compatibility (no longer used). Returns list[vector]."""
    if not texts:
        return []
    m = _get_model(model)
    vecs = m.encode(list(texts), show_progress_bar=False, normalize_embeddings=False)
    return [[float(x) for x in v] for v in vecs]


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _sig(kf):
    """A cheap fingerprint of the frame texts so a stale cache is rebuilt when the
    memory changes (frames added / re-captioned)."""
    h = hashlib.sha1()
    h.update(str(len(kf)).encode())
    for m in kf[:200]:
        h.update(frame_text(m)[:200].encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def load_or_build(kf, kf_path, host="http://127.0.0.1:11434", model=EMBED_MODEL):
    """Return {'vectors': [unit-vec per frame], 'model':...} for kf, cached beside
    kf_path. Rebuilds when the fingerprint changes. Returns None on any failure."""
    if not kf or not kf_path:
        return None
    cache = kf_path + ".semidx.json"
    sig = _sig(kf)
    try:
        if os.path.exists(cache):
            idx = json.load(open(cache))
            if idx.get("sig") == sig and idx.get("model") == model and \
               len(idx.get("vectors") or []) == len(kf):
                return idx
    except Exception:
        pass
    try:
        raw = embed_texts([frame_text(m) for m in kf], host=host, model=model)
        if len(raw) != len(kf):
            return None
        idx = {"sig": sig, "model": model, "vectors": [_norm(v) for v in raw]}
        try:
            json.dump(idx, open(cache, "w"))
        except Exception:
            pass
        return idx
    except Exception:
        return None


def retrieve(question, kf, kf_path, k=6, host="http://127.0.0.1:11434", model=EMBED_MODEL,
             index=None, min_score=0.0):
    """Top-k frames for the question by cosine similarity. Returns None if the
    semantic index is unavailable (caller falls back to IDF)."""
    idx = index if index is not None else load_or_build(kf, kf_path, host=host, model=model)
    if not idx:
        return None
    try:
        qv = _norm(embed_texts([question], host=host, model=model)[0])
    except Exception:
        return None
    vecs = idx["vectors"]
    scored = []
    for i, m in enumerate(kf):
        if i >= len(vecs):
            break
        s = sum(a * b for a, b in zip(qv, vecs[i]))
        if s >= min_score:
            scored.append((s, i, m))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, i, m in scored[:k]:
        mm = dict(m)
        mm["_sem_score"] = round(s, 4)
        out.append(mm)
    return out


def _selftest():
    import sys
    mem = sys.argv[2] if len(sys.argv) > 2 else \
        "data/walks/walk_outside_20260614/memory/kf_memory.json"
    kf = json.load(open(mem))
    for m in kf:
        o = m.get("ocr") or []
        m["_ocr_txt"] = "; ".join(x for x in o if x and str(x).strip()) if isinstance(o, list) else str(o)
    for q in ("what was the molecule?",
              "who was named on the poster of the molecule?",
              "whose name was on the X-Ray thing?"):
        top = retrieve(q, kf, mem, k=3)
        print("\nQ:", q)
        if top is None:
            print("  [semantic index unavailable]"); continue
        for m in top:
            print("  %.3f t=%s  %s" % (m["_sem_score"], m.get("t"),
                                       (frame_text(m)[:90]).replace("\n", " ")))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        _selftest()
