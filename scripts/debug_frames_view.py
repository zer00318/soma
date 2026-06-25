#!/usr/bin/env python3
"""TEST-ONLY frame viewer for the TRACE debug capture loop.

The native app (debug build) streams ~1 downscaled JPEG/sec to the Mac brain's
/debug/frame sink, which writes them under data/phone_captures/<moment>/debug_frames/.
This builds a contact-sheet montage + an animated GIF so the operator can SEE what
the camera actually captured. It exists purely for debugging — the product never
stores raw media.

    .venv/bin/python scripts/debug_frames_view.py [moment_id] [--out /tmp]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def _frames(moment: str) -> list[Path]:
    d = ROOT / "data" / "phone_captures" / moment / "debug_frames"
    return sorted(d.glob("*.jpg"), key=lambda p: p.name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("moment", nargs="?", default="live")
    ap.add_argument("--out", default="/tmp")
    ap.add_argument("--cols", type=int, default=5)
    args = ap.parse_args()

    paths = _frames(args.moment)
    if not paths:
        print(f"no debug frames for moment '{args.moment}'")
        return 1
    imgs = []
    for p in paths:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception as exc:  # a half-written or non-JPEG frame must not abort
            print(f"  skip {p.name}: {exc}")
    if not imgs:
        print("no decodable frames")
        return 1

    tw = 320
    thumbs = [im.resize((tw, int(im.height * tw / im.width))) for im in imgs]
    th = max(t.height for t in thumbs)
    cols = args.cols
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * th), (16, 16, 16))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols) * tw, (i // cols) * th))
    out = Path(args.out)
    sheet_path = out / f"trace_frames_{args.moment}_sheet.jpg"
    sheet.save(sheet_path, quality=85)

    gif_path = out / f"trace_frames_{args.moment}.gif"
    gframes = [im.resize((tw, int(im.height * tw / im.width))) for im in imgs]
    gframes[0].save(
        gif_path, save_all=True, append_images=gframes[1:], duration=500, loop=0
    )
    print(f"frames={len(imgs)}  sheet={sheet_path}  gif={gif_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
