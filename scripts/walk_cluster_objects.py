#!/usr/bin/env python3
"""Dedup crops into UNIQUE objects, then name each once.

The per-crop VLM approach named the same physical object dozens of times
(once per frame it appeared in) — slow and inconsistent. This embeds every
crop once with CLIP (fast, GPU-batched), groups crops that are visually the
same object, and names each group a single time against the vocabulary plus
"junk" anchors that let it reject walls/blur/shadows instead of forcing a
word. Output is one entry per unique object, in the same labels format the
inventory/fuse steps already consume.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

JUNK_ANCHORS = [
    "wall", "floor", "ceiling", "blurry photo", "motion blur", "shadow",
    "dark image", "out of focus", "hand", "human skin", "reflection",
    "nothing", "plain surface", "corner of a room", "carpet texture",
]


def time_of(frame_path: str) -> float:
    m = re.search(r"_(\d+\.\d+)s", os.path.basename(frame_path or ""))
    return float(m.group(1)) if m else 0.0


def load_vocab(path: str) -> list[str]:
    return [w.strip() for w in open(path, encoding="utf-8") if w.strip()]


def cluster_embeddings(embs, idxs, sim: float = 0.90):
    """Greedy nearest-centroid clustering. embs: (N,D) L2-normalized rows."""
    import numpy as np

    centroids: list = []   # running sum vectors
    counts: list[int] = []
    members: list[list[int]] = []
    for row, ci in zip(embs, idxs):
        if centroids:
            cmat = np.array([c / (np.linalg.norm(c) + 1e-9) for c in centroids])
            sims = cmat @ row
            j = int(sims.argmax())
            if sims[j] >= sim:
                centroids[j] = centroids[j] + row
                counts[j] += 1
                members[j].append(ci)
                continue
        centroids.append(row.copy())
        counts.append(1)
        members.append([ci])
    return centroids, counts, members


def name_centroids(centroids, vocab, anchors, text_feats, margin: float = 0.01, score_floor: float = 0.20):
    """Keep a cluster as a named object when its best VOCAB word clearly beats
    the best JUNK anchor (object-vs-not-object), NOT when two vocab synonyms
    tie. text_feats: (len(vocab)+len(anchors), D) normalized."""
    import numpy as np

    nv = len(vocab)
    out = []
    for s in centroids:
        v = s / (np.linalg.norm(s) + 1e-9)
        sims = text_feats @ v
        vocab_sims = sims[:nv]
        anchor_sims = sims[nv:] if len(sims) > nv else np.array([-1.0])
        vb = int(vocab_sims.argmax())
        vscore = float(vocab_sims[vb])
        ascore = float(anchor_sims.max())
        weak = vscore < score_floor
        junk_dominated = (vscore - ascore) < margin
        keep = not (weak or junk_dominated)
        out.append({
            "word": vocab[vb] if keep else None,
            "raw_best": vocab[vb],
            "score": vscore,
            "margin": float(vscore - ascore),
            "is_junk": bool(junk_dominated and not weak),
            "reject_reason": None if keep else ("weak_match" if weak else "looks_like_surface"),
        })
    return out


def build_clip(model_name="ViT-B-32", pretrained="laion2b_s34b_b79k"):
    import open_clip
    import torch
    from PIL import Image

    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    model = model.to(dev).eval()
    tokenizer = open_clip.get_tokenizer(model_name)
    return model, preprocess, tokenizer, dev, torch, Image


def run(crops, vocab, *, sim, margin, model_name, pretrained, progress=200):
    import numpy as np

    model, preprocess, tokenizer, dev, torch, Image = build_clip(model_name, pretrained)
    # 1) embed crops (batched)
    embs, idxs, buf = [], [], []

    def flush():
        if not buf:
            return
        x = torch.stack([b[1] for b in buf]).to(dev)
        with torch.no_grad():
            f = model.encode_image(x)
            f = f / f.norm(dim=-1, keepdim=True)
        for (i, _), vec in zip(buf, f.cpu().numpy()):
            embs.append(vec)
            idxs.append(i)
        buf.clear()

    for i, c in enumerate(crops):
        try:
            im = Image.open(c["crop"]).convert("RGB")
        except Exception:
            continue
        buf.append((i, preprocess(im)))
        if len(buf) >= 64:
            flush()
        if progress and i and i % progress == 0:
            print(f"embedded {i}/{len(crops)}", file=sys.stderr, flush=True)
    flush()
    embs = np.array(embs)
    print(f"embedded {len(embs)} crops -> clustering", file=sys.stderr, flush=True)

    # 2) cluster
    centroids, counts, members = cluster_embeddings(embs, idxs, sim=sim)
    print(f"{len(centroids)} unique-object clusters", file=sys.stderr, flush=True)

    # 3) name each cluster once
    texts = ["a photo of a " + w for w in vocab] + ["a photo of a " + a for a in JUNK_ANCHORS]
    with torch.no_grad():
        tf = model.encode_text(tokenizer(texts).to(dev))
        tf = (tf / tf.norm(dim=-1, keepdim=True)).cpu().numpy()
    named = name_centroids(centroids, vocab, JUNK_ANCHORS, tf, margin=margin)

    # 4) emit one labels-format record per surviving cluster (rep = first member)
    out_records = []
    kept = 0
    for cl, cnt, mem in zip(named, counts, members):
        rep = crops[mem[0]]
        rec = {
            "crop_path": rep["crop"],
            "crop": rep["crop"],
            "frame": rep.get("frame"),
            "box": rep.get("box"),
            "t": time_of(rep.get("frame")),
            "count": cnt,
            "score": cl["score"],
            "margin": cl["margin"],
        }
        if cl["word"] is None:
            rec.update({"word": "", "trust": "rejected", "reject_reason": cl.get("reject_reason") or "rejected"})
        else:
            rec.update({"word": cl["word"], "label": cl["word"]})
            kept += 1
        out_records.append(rec)
    return out_records, {"crops": len(crops), "clusters": len(centroids), "named_objects": kept}


def self_test() -> int:
    import numpy as np

    # two tight visual clusters + one stray
    a = np.array([1.0, 0.0, 0.0]); b = np.array([0.0, 1.0, 0.0])
    embs = np.array([a, a + 0.01, a - 0.01, b, b + 0.01])
    embs = np.array([e / np.linalg.norm(e) for e in embs])
    cents, counts, members = cluster_embeddings(embs, list(range(5)), sim=0.9)
    assert len(cents) == 2, f"expected 2 clusters got {len(cents)}"
    assert sorted(counts) == [2, 3], counts
    # naming: vocab match vs junk
    vocab = ["mug", "chair"]
    tf = np.array([
        a, b,                         # mug~clusterA, chair~clusterB
        np.array([0.0, 0.0, 1.0]),    # one junk anchor orthogonal
    ])
    tf = np.array([t / np.linalg.norm(t) for t in tf])
    named = name_centroids(cents, vocab, ["wall"], tf, margin=0.0)
    words = {n["word"] for n in named}
    assert "mug" in words and "chair" in words, words
    assert time_of("frame_000123_4.5s.jpg") == 4.5
    print("SELF-TEST PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crops", default="/tmp/walk_crops/crops_manifest.json")
    ap.add_argument("--vocab", default="ops/spatial_vocab.txt")
    ap.add_argument("--out", default="/tmp/walk_clustered_labels.json")
    ap.add_argument("--sim", type=float, default=0.90, help="cosine threshold to merge crops into one object")
    ap.add_argument("--margin", type=float, default=0.015)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="laion2b_s34b_b79k")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    crops = json.load(open(args.crops))
    if args.limit:
        crops = crops[: args.limit]
    records, stats = run(
        crops, load_vocab(args.vocab),
        sim=args.sim, margin=args.margin,
        model_name=args.model, pretrained=args.pretrained,
    )
    json.dump(records, open(args.out, "w"), indent=2)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
