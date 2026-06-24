#!/usr/bin/env python3
"""Committed pipeline (2026-06-13 plan): read-the-frame, not name-the-object.

For each keyframe: a Qwen2.5-VL attribute-rich CAPTION (objects/colors/layout)
PLUS verbatim Apple Vision OCR (the exact text on things). Two SEPARATE channels
stored per frame so reading-questions answer from OCR (never a guessed caption) —
that separation is what kills the 36% hallucination of the gemma-caption-only run.

Output: one NDJSON row per frame {t, frame, caption, ocr}. Checkpointed.
Run a 2-frame benchmark first:  --limit 2
"""
from __future__ import annotations
import argparse, glob, json, os, re, sys, time

MODEL = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
CAPTION_PROMPT = (
    "Describe this scene for later recall. List the real objects with their colors "
    "and materials, and the layout (what is on or next to what, left/right, fore/background). "
    "Be concrete and factual. Do NOT transcribe or guess any text, labels, or brand names "
    "— that is handled separately. ~80 words."
)

# Dense "extract everything" variant: the captures were under-extracting (generic scene
# summaries), so question-relevant detail (a held glasses case, a game controller, a person's
# clothing, a bag's zip state, keys on a table) never reached the brain. This pulls the moment
# speculatively-over-complete (north star §2) — solve the PRINCIPLE (extract all aspects), not
# the example. Still text-blind (OCR is a separate channel) so it can't fabricate labels.
CAPTION_PROMPT_DENSE = (
    "Extract EVERYTHING in this image for later recall — be exhaustive, concrete, factual. "
    "Cover, WHENEVER PRESENT:\n"
    "(1) PEOPLE — each person, what they wear (garment + color), what they hold or are doing;\n"
    "(2) DEVICES / SCREENS — laptop, phone, tablet, game console, controller, TV, monitor: the "
    "TYPE and broadly what is on the screen;\n"
    "(3) VEHICLES — type and any make/model/body-shape cues (pickup, sedan, bus);\n"
    "(4) HELD or WORN — anything in a hand, on a wrist (watch), on the face (glasses), a bag and "
    "whether it looks open or closed;\n"
    "(5) ON SURFACES — what sits on tables/desks/counters/beds (keys, cases, cups, papers, bedding);\n"
    "(6) LAYOUT — left/right, fore/background, what is on or next to what.\n"
    "State colors and materials. If something is ambiguous or you are unsure, say so plainly. "
    "Do NOT transcribe or guess any text, labels, or brand names — that is a separate channel. ~140 words."
)

# Counting-aware variant: fix counting at the SEEING stage (where the pixels are),
# not the text-merge stage. Used by the overnight re-caption (--counting).
CAPTION_PROMPT_COUNT = (
    "Describe this scene for later recall, focusing on COUNTING and DISTINGUISHING. "
    "For every group of similar objects, state exactly HOW MANY you can see in THIS image "
    "and what makes each one different (e.g. 'three jars: two appear empty, one looks full'; "
    "'four shirts: pink, blue, black, white'). List all objects with colors/materials and the "
    "layout (left/right, what's on what). Be precise about quantities you can actually see. "
    "Do NOT read or guess any text/labels/brands — that's handled separately. ~100 words."
)


def time_of(path: str) -> float:
    m = re.search(r"_(\d+\.\d+)s", os.path.basename(path or ""))
    return float(m.group(1)) if m else 0.0


def downscale(path, max_dim=1280):
    """Resize once to a temp file; feeds both caption and OCR (4K is slow/leaky)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(1.0, max_dim / max(w, h))
    if s < 1.0:
        im = im.resize((int(w * s), int(h * s)))
    tmp = "/tmp/_kf_%d.jpg" % (abs(hash(path)) % 10_000_000)
    im.save(tmp, quality=90)
    return tmp


def load_captioner():
    from mlx_vlm import load
    from transformers import AutoImageProcessor
    model, processor = load(MODEL)
    # mlx-vlm 0.1.15 fix: transformers defaults to the fast Qwen2-VL image processor
    # which mlx can't feed ("Only PyTorch tensors supported"). Force the slow one,
    # but keep load()'s processor (it carries the detokenizer).
    processor.image_processor = AutoImageProcessor.from_pretrained(MODEL, use_fast=False)
    return model, processor


_CFG = None


def caption(model, processor, img_path, max_tokens=160, caption_prompt=CAPTION_PROMPT):
    global _CFG
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    if _CFG is None:
        _CFG = load_config(MODEL)
    prompt = apply_chat_template(processor, _CFG, caption_prompt, num_images=1)
    try:
        out = generate(model, processor, prompt, [img_path], max_tokens=max_tokens,
                       temperature=0.0, verbose=False)
    except TypeError:
        out = generate(model, processor, prompt, image=[img_path], max_tokens=max_tokens,
                       verbose=False)
    return (out.text if hasattr(out, "text") else str(out)).strip()


def ocr(img_path, min_conf=0.3):
    from ocrmac import ocrmac
    res = ocrmac.OCR(img_path, recognition_level="accurate").recognize()
    lines = [t.strip() for (t, conf, _box) in res if conf >= min_conf and t.strip()]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-dir", default="data/walks/home_capture_20260613/work/run_frames")
    ap.add_argument("--out", default="data/walks/home_capture_20260613/memory/kf_memory.json")
    ap.add_argument("--dedup-thresh", type=float, default=14.0)
    ap.add_argument("--cap", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="benchmark: only N frames")
    ap.add_argument("--counting", action="store_true",
                    help="use the counting-aware caption prompt (overnight re-caption)")
    ap.add_argument("--dense", action="store_true",
                    help="use the dense 'extract everything' prompt (people/devices/held/surfaces)")
    args = ap.parse_args()
    cap_prompt = (CAPTION_PROMPT_DENSE if args.dense
                  else CAPTION_PROMPT_COUNT if args.counting else CAPTION_PROMPT)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    # reuse describe_walk's cheap dedup so we caption DISTINCT scenes only
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from describe_walk import pick_keyframes
    from post_capture_identity import checkpoint_rows, job_run_id
    frames = sorted(glob.glob(os.path.join(args.frames_dir, "*.jpg")), key=time_of)
    keys = pick_keyframes(frames, args.dedup_thresh, args.cap)
    if args.limit:
        keys = keys[:args.limit]
    print(f"{len(frames)} frames -> {len(keys)} distinct keyframes", file=sys.stderr, flush=True)

    memory_dir = os.path.dirname(os.path.abspath(args.out))
    run_id = job_run_id(
        memory_dir, "keyframe_memory", 2, MODEL, cap_prompt,
        {"dedup_thresh": args.dedup_thresh, "cap": args.cap, "limit": args.limit}, keys)

    ckpt = args.out + ".ckpt.ndjson"
    done = checkpoint_rows(ckpt, run_id)
    if os.path.exists(ckpt):
        print(f"resume: {len(done)} done", file=sys.stderr, flush=True)

    print("loading Qwen2.5-VL...", file=sys.stderr, flush=True)
    model, processor = load_captioner()

    fh = open(ckpt, "a")
    memory, t_cap, t_ocr = [], [], []
    for i, f in enumerate(keys, 1):
        if f in done:
            memory.append(done[f]); continue
        try:
            small = downscale(f)
            t0 = time.time(); cap = caption(model, processor, small, caption_prompt=cap_prompt); t_cap.append(time.time() - t0)
            t0 = time.time(); txt = ocr(small); t_ocr.append(time.time() - t0)
            os.remove(small)
        except Exception as e:
            print(f"  err {f}: {e}", file=sys.stderr, flush=True); continue
        rec = {"t": time_of(f), "frame": f, "caption": cap, "ocr": txt,
               "_run_id": run_id}
        memory.append(rec); fh.write(json.dumps(rec) + "\n"); fh.flush()
        print(f"[{i}/{len(keys)}] {time_of(f):.1f}s  cap={t_cap[-1]:.1f}s ocr={t_ocr[-1]:.1f}s  "
              f"OCR:{txt[:80]}", file=sys.stderr, flush=True)
    fh.close()
    memory.sort(key=lambda r: r["t"])
    json.dump(memory, open(args.out, "w"), indent=2, ensure_ascii=False)
    if t_cap:
        print(f"\nBENCHMARK caption avg {sum(t_cap)/len(t_cap):.1f}s/frame, "
              f"ocr avg {sum(t_ocr)/len(t_ocr):.2f}s/frame", file=sys.stderr)
    print(f"WROTE {len(memory)} keyframe memories to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
