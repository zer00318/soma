#!/usr/bin/env python3
"""Proxy test: does the ON-DEVICE VLM (Qwen2.5-VL-3B-4bit, MLX) label region crops as well as the
Mac gemma3-27B? "FastVLM is shit" was the objection — this checks whether a *good* on-device VLM
(the one that actually runs on iPhone 17 via MLX) clears the bar. Reuses the anchor boxes the
coordinate-first pipeline already produced, so we compare label quality head-to-head.

    .venv/bin/python scripts/ondevice_label_probe.py <frame.jpg> <perceive_json>
"""
import sys, json
from pathlib import Path
from PIL import Image

def main():
    frame, pjson = sys.argv[1], sys.argv[2]
    anchors = json.loads(Path(pjson).read_text())
    img = Image.open(frame).convert("RGB")

    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    model, processor = load("mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
    config = model.config if hasattr(model, "config") else processor

    prompt = ("Name the single main object in this cropped photo in 1-3 words (a plain noun like "
              "'steel thermos', 'book', 'backpack'). If it is only wall/floor/surface say 'surface'. "
              "Answer with only the noun.")
    print(f"{'gemma3-27B (Mac)':22} -> {'Qwen2.5-VL-3B (on-device)':26} | coord (x,y,z) size")
    scratch = Path("/private/tmp/odl"); scratch.mkdir(exist_ok=True)
    for i, a in enumerate(anchors):
        box = a["box_xyxy"]
        crop = img.crop(box)
        cp = scratch / f"c{i}.jpg"; crop.save(cp)
        try:
            formatted = apply_chat_template(processor, config, prompt, num_images=1)
            out = generate(model, processor, formatted, [str(cp)], max_tokens=12, verbose=False)
            label = (out.text if hasattr(out, "text") else str(out)).strip().strip(".").lower()[:30]
        except Exception as e:
            label = f"ERR {type(e).__name__}"
        gem = a["helpers"]["label"]["label"]
        c = a["coordinate_m"]; s = a["size_m"]
        print(f"{gem:22} -> {label:26} | ({c[0]:+.2f},{c[1]:+.2f},{c[2]:.2f}) {s[0]:.2f}x{s[1]:.2f}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
