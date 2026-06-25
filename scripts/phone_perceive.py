#!/usr/bin/env python3
"""Phone-capture perception: posted JPEG frames -> Apple Vision OCR -> kf_memory.json.

The honest, high-precision core: READ what you saw. trace_app deletes the frames right
after, so only derived TEXT persists (the no-raw-media moat holds live). We deliberately do
NOT add a verbose VLM caption here: it was measured 4 ways to RAISE hallucination (the brain
confabulates from fluent prose). OCR + the brain's cross-frame consensus = read-or-refuse,
which is the product's whole moat. (Richer BOUND helpers can be layered later, gated by
confidence — never loose prose.)

perceive_frames(paths, times, mdir) -> {frames, text_lines, sample}
"""
from __future__ import annotations

import json
import os


def _ocr(path, min_conf=0.3):
    """Apple Vision OCR via ocrmac (same call as build_keyframe_memory.ocr)."""
    try:
        from ocrmac import ocrmac
        res = ocrmac.OCR(path, recognition_level="accurate").recognize()
        return [t.strip() for (t, conf, _box) in res if conf >= min_conf and t.strip()]
    except Exception:
        return []


def perceive_frames(paths, times, mdir):
    recs = []
    for i, (p, t) in enumerate(zip(paths, times)):
        texts = _ocr(p)
        recs.append({"t": float(t), "frame": "f_%d" % i, "ocr": texts,
                     "caption": "", "source": "phone_ocr"})
    os.makedirs(mdir, exist_ok=True)
    with open(os.path.join(mdir, "kf_memory.json"), "w") as fh:
        json.dump(recs, fh, indent=2, ensure_ascii=False)
    lines = [t for r in recs for t in r["ocr"]]
    return {"frames": len(recs), "text_lines": len(lines), "sample": lines[:8]}
