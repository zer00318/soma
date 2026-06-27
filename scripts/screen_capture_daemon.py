#!/usr/bin/env python3
"""Mac screen-capture daemon — the DIGITAL-LIFE capture channel.

Camera-films-screen cannot resolve UI text (proven on real captures: YouTube
titles, chat messages, read receipts are all sub-legible). Real OS-level screen
capture + Apple Vision OCR reads them PERFECTLY. This daemon is that channel.

Loop: grab the screen -> Apple Vision OCR -> write a typed observation into the
TraceMemoryStore -> DELETE the screenshot immediately. Only derived TEXT persists
(no raw image ever stored or egressed — the privacy moat holds for digital too).

Dedup: consecutive near-identical screens are skipped so the store isn't flooded
with 1000 copies of a static page; a meaningfully-changed screen writes a new
observation with the frontmost app as context.

Run (24/7, cheap — OCR is local + fast, no LLM):
    .venv/bin/python scripts/screen_capture_daemon.py --store data/trace_store.sqlite3 --interval 4
Single shot (test):
    .venv/bin/python scripts/screen_capture_daemon.py --store /tmp/t.sqlite3 --once
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evaluation.vision_ocr import ocr_image  # noqa: E402  Apple Vision OCR (local, verbatim)
from trace_memory.store import TraceMemoryStore  # noqa: E402


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] SCREEN {msg}", flush=True)


def frontmost_app() -> str:
    """Best-effort frontmost application name (context for the observation)."""
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first application process whose frontmost is true'],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def grab_and_ocr(tmp_dir: Path) -> tuple[list[str], str]:
    """Capture the screen, OCR it, delete the image. Returns (lines, app)."""
    shot = tmp_dir / f"_screen_{uuid.uuid4().hex}.jpg"
    try:
        # -x: no sound. -t jpg. Captures the main display.
        subprocess.run(["screencapture", "-x", "-t", "jpg", str(shot)],
                       check=True, capture_output=True, timeout=15)
        app = frontmost_app()
        lines = ocr_image(str(shot))
        return lines, app
    finally:
        try:
            shot.unlink()  # privacy: the raw image never survives perception
        except FileNotFoundError:
            pass


def _token_set(text: str) -> set[str]:
    return {t for t in text.lower().split() if len(t) > 2}


def _similar(a: str, b: str, threshold: float = 0.92) -> bool:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return a.strip() == b.strip()
    jac = len(sa & sb) / len(sa | sb)
    return jac >= threshold


def run(store_path: str, interval: float, once: bool, min_chars: int) -> int:
    store = TraceMemoryStore(store_path)
    tmp_dir = Path(os.environ.get("TMPDIR", "/tmp"))
    _log(f"daemon up. store={store_path} interval={interval}s embedder={store.retrieval_mode}")
    last_text = ""
    written = 0
    try:
        while True:
            t0 = time.time()
            try:
                lines, app = grab_and_ocr(tmp_dir)
            except Exception as exc:  # noqa: BLE001  one bad grab must not kill the daemon
                _log(f"grab/ocr error: {exc}")
                if once:
                    return 1
                time.sleep(interval)
                continue
            text = "\n".join(line for line in lines if line.strip())
            if len(text) < min_chars:
                _log(f"skip: only {len(text)} chars (app={app})")
            elif _similar(text, last_text):
                _log(f"skip: near-duplicate of last (app={app})")
            else:
                obs_text = f"SCREEN [{app}]\n{text}"
                store.write_observation(
                    text=obs_text,
                    t_ms=int(time.time() * 1000),
                    source="mac_screen",
                    place=f"app:{app}",
                    provenance={"channel": "mac_screen_ocr", "app": app},
                    metadata={"app": app, "line_count": len(lines), "char_count": len(text)},
                )
                last_text = text
                written += 1
                preview = text.replace("\n", " ")[:90]
                _log(f"wrote obs #{written} app={app} chars={len(text)} | {preview}")
            if once:
                return 0
            dt = time.time() - t0
            time.sleep(max(0.0, interval - dt))
    except KeyboardInterrupt:
        _log(f"stopped. wrote {written} observations.")
        return 0
    finally:
        store.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="data/trace_store.sqlite3")
    ap.add_argument("--interval", type=float, default=4.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--min-chars", type=int, default=12)
    args = ap.parse_args()
    return run(args.store, args.interval, args.once, args.min_chars)


if __name__ == "__main__":
    raise SystemExit(main())
