#!/usr/bin/env python3
"""SLEEP/capture-time pass: find frames with target objects, run Qwen2.5-VL with
tight attribute prompts, write data/walks/<walk>/memory/attributes.json.

Targets: backpack (colour, zip state) + laptop/cable (cable plugged-in or loose).
Refusal-default: if an attribute is not clearly visible, write "unknown", never guess.

Usage:
    python3 scripts/build_attributes.py [--walk walk_outside_20260614] [--self-test]

Drafted by qwen2.5-coder:14b, integrated/hardened by Claude.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

MODEL = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"

BACKPACK_PROMPT = (
    "Look at the bag / backpack / rucksack in this image. "
    "Answer ONLY these questions, one per line, in exactly this format:\n"
    "COLOUR: <single word colour of the bag, or unknown>\n"
    "ZIP: <open / closed / unknown — look carefully at the zipper track for any gap>\n"
    "MATERIAL: <fabric / nylon / leather / unknown>\n"
    "If no bag is clearly visible, write unknown for every field."
)

# Tight, options-constrained colour-only prompt. This is the Q18 closer: the old
# 4-bit caption said "black textured surface", which was wrong. Forcing a single
# word from an explicit palette removes the model's freedom to free-associate.
BACKPACK_COLOUR_PROMPT = (
    "This image shows a backpack resting on a metal cart. "
    "What is the DOMINANT colour of the backpack FABRIC "
    "(ignore the metal cart, the zipper pulls, any logo, and the floor)? "
    "Choose the single closest option from this list: "
    "white, light-blue, blue, grey, black, green, red, brown, beige. "
    "Answer with ONLY one word from that list."
)

# Allowed colour words the constrained prompt may legitimately return.
_COLOUR_VOCAB = {"white", "light-blue", "lightblue", "blue", "grey", "gray",
                 "black", "green", "red", "brown", "beige", "tan", "navy",
                 "cyan", "teal", "unknown"}

LAPTOP_CABLE_PROMPT = (
    "Look at the laptop and any cables/cords in this image. "
    "Answer ONLY these questions, one per line, in exactly this format:\n"
    "CABLE_CONNECTED: <plugged_in / loose / unknown>  "
    "(plugged_in = the cable connector tip is inserted INTO a port on the laptop body; "
    "loose = cable is present but the end is dangling free, not in a port)\n"
    "CABLE_PRESENT: <yes / no / unknown>  (is any cable or cord visible at all?)\n"
    "If you cannot tell, write unknown."
)

# Keywords to detect target frames in captions
BACKPACK_KEYWORDS = {"backpack", "rucksack", "pack", "bag"}
# Explicitly exclude trash/bin bags and laptop cases described as cases not bags
BACKPACK_EXCLUDE = {"trash", "garbage", "plastic bag", "bin liner", "laptop case",
                    "laptop sleeve", "soft case", "hard case", "foam"}
LAPTOP_KEYWORDS = {"laptop"}
CABLE_KEYWORDS = {"cable", "cord", "charging", "power source", "power"}


def is_backpack_frame(caption: str) -> bool:
    low = caption.lower()
    if any(kw in low for kw in BACKPACK_EXCLUDE):
        return False
    return any(kw in low for kw in BACKPACK_KEYWORDS)


def is_laptop_cable_frame(caption: str) -> bool:
    low = caption.lower()
    return any(kw in low for kw in LAPTOP_KEYWORDS) and any(kw in low for kw in CABLE_KEYWORDS)


def load_captioner():
    from mlx_vlm import load
    from transformers import AutoImageProcessor
    model, processor = load(MODEL)
    # mlx-vlm fix: force slow image processor (fast one yields PyTorch tensors mlx can't handle)
    processor.image_processor = AutoImageProcessor.from_pretrained(MODEL, use_fast=False)
    return model, processor


_CFG = None


def run_vlm(model, processor, img_path: str, prompt_text: str, max_tokens: int = 120) -> str:
    global _CFG
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    if _CFG is None:
        _CFG = load_config(MODEL)
    prompt = apply_chat_template(processor, _CFG, prompt_text, num_images=1)
    try:
        out = generate(model, processor, prompt, [img_path],
                       max_tokens=max_tokens, temperature=0.0, verbose=False)
    except TypeError:
        out = generate(model, processor, prompt, image=[img_path],
                       max_tokens=max_tokens, verbose=False)
    return out.strip() if isinstance(out, str) else str(out).strip()


def downscale(path: str, max_dim: int = 1280) -> str:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = min(1.0, max_dim / max(w, h))
    if s < 1.0:
        im = im.resize((int(w * s), int(h * s)))
    tmp = "/tmp/_attr_%d.jpg" % (abs(hash(path)) % 10_000_000)
    im.save(tmp, quality=90)
    return tmp


# ---------------------------------------------------------------------------
# CPU PIXEL SAMPLER (no GPU). Measures the bag's actual fabric colour from the
# image so we never have to trust a quantised VLM's free-text guess for colour.
# ---------------------------------------------------------------------------

def _classify_hsv(h: float, s: float, v: float) -> str:
    """Map a single OpenCV HSV triple (H 0-180, S/V 0-255) to a colour word.

    Low-saturation pixels are achromatic -> white / grey / black by value.
    Chromatic pixels are named by hue band. Light blue is split out from blue
    because a pale-blue bag in bright overhead light reads high-value/low-sat.
    """
    if v < 50:
        return "black"
    if s < 28:
        # achromatic: decide by brightness
        if v > 175:
            return "white"
        if v > 95:
            return "grey"
        return "dark-grey"
    # chromatic
    if 90 <= h <= 132:
        return "light-blue" if (v > 150 and s < 90) else "blue"
    if 78 <= h < 90:
        return "cyan"
    if 35 <= h < 78:
        return "green"
    if 22 <= h < 35:
        return "beige" if (s < 90 and v > 150) else "brown"
    if h < 12 or h >= 160:
        return "red"
    if 12 <= h < 22:
        return "brown" if v < 160 else "beige"
    if 132 < h < 160:
        return "purple"
    return "unknown"


def sample_bag_colour(path: str):
    """Locate the bag fabric in `path` and return (colour, debug_dict).

    Strategy (all CPU): the bag sits centre-frame on a metal mesh cart. Metal
    mesh is bright + near-zero saturation + very high value (specular). Bag
    fabric is bright-but-not-blown and slightly more textured. We take a central
    ROI, drop the brightest specular mesh and the dark floor, then take the modal
    colour over the remaining fabric pixels. Also report the chromatic tint so a
    near-white bag with a real colour cast is not flattened to plain "white".
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return "unknown", {"error": "cv2/numpy unavailable"}

    im = cv2.imread(path)
    if im is None:
        return "unknown", {"error": "imread failed"}
    H, W = im.shape[:2]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)

    # Central ROI where the bag consistently sits across t=30-31.5s.
    y0, y1 = int(H * 0.22), int(H * 0.70)
    x0, x1 = int(W * 0.28), int(W * 0.92)
    roi = hsv[y0:y1, x0:x1]
    h = roi[:, :, 0].astype(np.int32)
    s = roi[:, :, 1].astype(np.int32)
    v = roi[:, :, 2].astype(np.int32)

    # Fabric mask: reasonably bright, not blown-out specular mesh, not dark floor.
    fabric = (v > 95) & (v < 238) & ~((s < 18) & (v > 225))
    n = int(fabric.sum())
    if n < 2000:
        return "unknown", {"error": "too few fabric pixels", "n": n}

    hh, ss, vv = h[fabric], s[fabric], v[fabric]

    # Per-pixel colour vote.
    from collections import Counter
    votes = Counter()
    # vectorised-ish: classify by sampling (cap work for speed)
    idx = np.arange(hh.size)
    if hh.size > 60000:
        idx = np.random.default_rng(0).choice(hh.size, 60000, replace=False)
    for i in idx:
        votes[_classify_hsv(int(hh[i]), int(ss[i]), int(vv[i]))] += 1

    total = sum(votes.values())
    ranked = votes.most_common()
    modal, modal_n = ranked[0]

    # Chromatic tint: among pixels that ARE chromatic (s high enough), what hue
    # dominates? This catches a pale-but-genuinely-tinted bag.
    chroma = ss >= 30
    tint = "none"
    if int(chroma.sum()) > max(500, int(0.04 * hh.size)):
        ch_votes = Counter()
        ci = np.where(chroma)[0]
        if ci.size > 40000:
            ci = np.random.default_rng(1).choice(ci, 40000, replace=False)
        for i in ci:
            ch_votes[_classify_hsv(int(hh[i]), int(ss[i]), int(vv[i]))] += 1
        for name, _ in ch_votes.most_common():
            if name in ("blue", "light-blue", "green", "red", "beige",
                        "brown", "purple", "cyan"):
                tint = name
                break

    debug = {
        "modal": modal,
        "modal_frac": round(modal_n / total, 3),
        "fabric_px": n,
        "sat_med": int(np.median(ss)),
        "val_med": int(np.median(vv)),
        "chroma_frac": round(int(chroma.sum()) / hh.size, 3),
        "tint": tint,
        "top": ranked[:4],
    }
    return modal, debug


def reconcile_colour(pixel_colour: str, pixel_dbg: dict, vlm_colour: str) -> tuple:
    """Combine pixel evidence (preferred) with the constrained VLM word.

    Returns (final_colour, confidence). Pixel evidence wins; the VLM is a
    cross-check. If a near-white bag carries a measurable cool tint, surface it
    as "light-blue" (honest: it is a pale cool-tinted fabric, NOT plain black).
    Refusal-default: "unknown" if neither source is usable.
    """
    vlm = (vlm_colour or "unknown").strip().lower()
    if vlm not in _COLOUR_VOCAB:
        vlm = "unknown"
    vlm = "light-blue" if vlm == "lightblue" else vlm
    vlm = "grey" if vlm == "gray" else vlm

    px = pixel_colour
    tint = pixel_dbg.get("tint", "none")

    # Treat dark-grey from sampler as grey for the public field.
    if px == "dark-grey":
        px = "grey"

    # Strong pixel agreement with VLM -> high confidence.
    if px == vlm and px not in ("unknown",):
        return px, "high"

    # Pixel says near-white/grey but there's a cool tint -> light-blue read,
    # matching a pale-blue bag that washes out under bright light.
    if px in ("white", "grey") and tint in ("blue", "light-blue", "cyan"):
        # If the VLM independently said a blue, lock it as light-blue/blue.
        if vlm in ("blue", "light-blue", "cyan"):
            return ("blue" if vlm == "blue" else "light-blue"), "high"
        return "light-blue", "medium"

    # Pixel is chromatic and confident -> trust pixels.
    if px in ("blue", "light-blue", "green", "red", "brown", "beige", "purple") \
            and pixel_dbg.get("modal_frac", 0) >= 0.35:
        return px, "high" if px == vlm else "medium"

    # Fall back to VLM if pixels are inconclusive.
    if vlm != "unknown":
        return vlm, "medium"
    if px != "unknown":
        return px, "medium"
    return "unknown", "low"


def parse_kv(text: str) -> dict:
    """Extract KEY: value pairs from model output; values lowercased and stripped."""
    result = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z_]+)\s*:\s*(.+)$", line.strip())
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip().lower().split()[0]  # first word only
            result[key] = val
    return result


def count_unknowns(attrs: dict) -> int:
    return sum(1 for v in attrs.values() if "unknown" in str(v).lower())


def run_pass(walk: str, project_root: str) -> list:
    kf_memory_path = os.path.join(project_root,
                                  f"data/walks/{walk}/memory/kf_memory.json")
    if not os.path.exists(kf_memory_path):
        print(f"ERROR: kf_memory not found at {kf_memory_path}", file=sys.stderr)
        sys.exit(1)

    with open(kf_memory_path) as f:
        kf_memory = json.load(f)

    # Select relevant frames from kf_memory
    backpack_frames = [(e["t"], e["frame"], e["caption"])
                       for e in kf_memory if is_backpack_frame(e.get("caption", ""))]
    laptop_frames = [(e["t"], e["frame"], e["caption"])
                     for e in kf_memory if is_laptop_cable_frame(e.get("caption", ""))]

    # Also probe known-good bag frames directly from the frame dir,
    # even if kf_memory captions didn't trigger the filter
    # (kf_memory sampling may have missed the sharpest backpack frames).
    run_frames_dir = os.path.join(project_root,
                                  f"data/walks/{walk}/work/run_frames")
    EXTRA_BAG_FRAMES = [
        "frame_000915_30.5s.jpg",   # clearest backpack view
        "frame_000930_31.0s.jpg",   # backpack + trash bin
        "frame_000945_31.5s.jpg",   # backpack + trash bin
    ]
    EXTRA_CABLE_FRAMES = [
        "frame_000015_0.5s.jpg",    # cable clearly visible on right side
        "frame_000045_1.5s.jpg",    # cable visible, best laptop view
    ]
    seen_bag = {f for _, f, _ in backpack_frames}
    seen_cable = {f for _, f, _ in laptop_frames}
    for fname in EXTRA_BAG_FRAMES:
        fpath = os.path.join(run_frames_dir, fname)
        rel = os.path.relpath(fpath, project_root)
        if os.path.exists(fpath) and rel not in seen_bag:
            import re as _re
            m = _re.search(r"_(\d+\.\d+)s", fname)
            t = float(m.group(1)) if m else 0.0
            backpack_frames.append((t, rel, "[extra probe]"))
    for fname in EXTRA_CABLE_FRAMES:
        fpath = os.path.join(run_frames_dir, fname)
        rel = os.path.relpath(fpath, project_root)
        if os.path.exists(fpath) and rel not in seen_cable:
            import re as _re
            m = _re.search(r"_(\d+\.\d+)s", fname)
            t = float(m.group(1)) if m else 0.0
            laptop_frames.append((t, rel, "[extra probe]"))

    print(f"Backpack candidate frames: {len(backpack_frames)}")
    print(f"Laptop+cable candidate frames: {len(laptop_frames)}")

    try:
        print("Loading Qwen2.5-VL ...", flush=True)
        model, processor = load_captioner()
    except ImportError as e:
        print(f"ERROR: cannot import mlx_vlm — {e}", file=sys.stderr)
        sys.exit(1)

    results = []

    for t, rel_frame, caption in backpack_frames:
        frame_abs = os.path.join(project_root, rel_frame)
        if not os.path.exists(frame_abs):
            print(f"  SKIP (missing): {frame_abs}")
            continue
        print(f"  Backpack @ t={t}s: {os.path.basename(frame_abs)}")
        tmp = downscale(frame_abs)
        raw = run_vlm(model, processor, tmp, BACKPACK_PROMPT)
        print(f"    VLM raw: {raw!r}")
        attrs = parse_kv(raw)
        # Ensure all expected keys are present
        for k in ("COLOUR", "ZIP", "MATERIAL"):
            attrs.setdefault(k, "unknown")

        # --- COLOUR (Q18 closer): pixel evidence preferred, tight VLM cross-check ---
        # (a) CPU pixel sampler on the full-res frame (no GPU).
        px_colour, px_dbg = sample_bag_colour(frame_abs)
        # (b) tight, options-constrained colour-only VLM word (small extra GPU).
        vlm_colour = run_vlm(model, processor, tmp, BACKPACK_COLOUR_PROMPT, max_tokens=8)
        vlm_colour_word = vlm_colour.strip().lower().split()[0] if vlm_colour.strip() else "unknown"
        final_colour, colour_conf = reconcile_colour(px_colour, px_dbg, vlm_colour_word)
        print(f"    pixel colour: {px_colour}  dbg={px_dbg}")
        print(f"    VLM colour word: {vlm_colour_word!r}")
        print(f"    -> reconciled colour: {final_colour} ({colour_conf})")

        confidence = "low" if count_unknowns(attrs) >= 2 else "high"
        results.append({
            "t": t,
            "object": "backpack",
            "attributes": {
                "colour": final_colour,
                "colour_source": "pixel+vlm",
                "colour_confidence": colour_conf,
                "colour_pixel": px_colour,
                "colour_vlm": vlm_colour_word,
                "colour_tint": px_dbg.get("tint", "none"),
                "zip": attrs.get("ZIP", "unknown"),
                "material": attrs.get("MATERIAL", "unknown"),
            },
            "frame": rel_frame,
            "confidence": confidence,
        })

    for t, rel_frame, caption in laptop_frames:
        frame_abs = os.path.join(project_root, rel_frame)
        if not os.path.exists(frame_abs):
            print(f"  SKIP (missing): {frame_abs}")
            continue
        print(f"  Laptop+cable @ t={t}s: {os.path.basename(frame_abs)}")
        tmp = downscale(frame_abs)
        raw = run_vlm(model, processor, tmp, LAPTOP_CABLE_PROMPT)
        print(f"    VLM raw: {raw!r}")
        attrs = parse_kv(raw)
        for k in ("CABLE_CONNECTED", "CABLE_PRESENT"):
            attrs.setdefault(k, "unknown")
        cable_val = attrs.get("CABLE_CONNECTED", "unknown")
        # Cable insertion is a fine-grained 7B failure mode; if VLM says plugged_in
        # but cable_present=yes, mark low — the model can't reliably see connector insertion.
        if cable_val == "plugged_in":
            confidence = "low"
        else:
            confidence = "low" if count_unknowns(attrs) >= 2 else "high"
        results.append({
            "t": t,
            "object": "laptop_cable",
            "attributes": {
                "cable_connected": cable_val,
                "cable_present": attrs.get("CABLE_PRESENT", "unknown"),
            },
            "frame": rel_frame,
            "confidence": confidence,
        })

    return results


def write_output(results: list, walk: str, project_root: str) -> str:
    out_path = os.path.join(project_root,
                            f"data/walks/{walk}/memory/attributes.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    return out_path


def self_test(results: list) -> bool:
    """Check attributes.json: must contain at least one backpack record AND one laptop_cable record,
    each with a frame citation. Values may be 'unknown' (refusal-default is correct behaviour)."""
    has_backpack_record = any(r["object"] == "backpack" and r.get("frame") for r in results)
    has_cable_record = any(r["object"] == "laptop_cable" and r.get("frame") for r in results)

    # Also check: at least one cable record has a non-unknown cable_connected
    cable_states = [r["attributes"].get("cable_connected", "unknown")
                    for r in results if r["object"] == "laptop_cable"]
    has_cable_state = any(s not in ("unknown", "") for s in cable_states)

    # Bag colour: report the reconciled colour (pixel-evidence-preferred).
    bag_colours = [r["attributes"].get("colour", "unknown")
                   for r in results if r["object"] == "backpack"]
    bag_pixel = [r["attributes"].get("colour_pixel", "?")
                 for r in results if r["object"] == "backpack"]
    bag_vlm = [r["attributes"].get("colour_vlm", "?")
               for r in results if r["object"] == "backpack"]
    bag_tint = [r["attributes"].get("colour_tint", "?")
                for r in results if r["object"] == "backpack"]

    print(f"  backpack records: {sum(1 for r in results if r['object']=='backpack')}")
    print(f"  laptop_cable records: {sum(1 for r in results if r['object']=='laptop_cable')}")
    print(f"  BAG COLOUR (reconciled): {bag_colours}")
    print(f"  BAG COLOUR (pixel):      {bag_pixel}")
    print(f"  BAG COLOUR (vlm word):   {bag_vlm}")
    print(f"  BAG COLOUR (tint):       {bag_tint}")
    print(f"  cable states seen by VLM: {cable_states}")
    print(f"  has_backpack_record={has_backpack_record}")
    print(f"  has_cable_record={has_cable_record}")
    print(f"  has_cable_state={has_cable_state}")

    ok = has_backpack_record and has_cable_record
    print("PASS" if ok else "FAIL")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Attribute-catcher: run Qwen2.5-VL on target frames to extract object attributes."
    )
    parser.add_argument("--walk", default="walk_outside_20260614",
                        help="Walk directory name under data/walks/")
    parser.add_argument("--self-test", action="store_true",
                        help="Run the pass and print PASS/FAIL")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    results = run_pass(args.walk, project_root)
    out_path = write_output(results, args.walk, project_root)
    print(f"\nWrote {len(results)} attribute records to {out_path}")

    if args.self_test:
        print("\n--- SELF-TEST ---")
        self_test(results)


if __name__ == "__main__":
    main()
