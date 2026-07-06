#!/usr/bin/env python3
"""P20 — Mac screen daemon: the digital pillar (half the founder's waking day).

Standing helper. Captures the Mac's OWN screen, OCRs it with Vision (native
screenshot OCR is proven; camera-films-screen was what failed), tracks
frontmost app + window title, and POSTs P02-contract observations to the hub.

LAWS (packet P20):
- L1: pixels are captured ON the Mac and DELETED right after OCR — only text +
  metadata persist. The PNG lives seconds, in a private tmp dir.
- L5: no app-specific content parsing — verbatim OCR spans only.
- Privacy: the TRACE app's own windows are excluded (feedback loop).

Cadence: cheap frontmost poll every POLL_S; a capture fires on focus change or
every CAPTURE_S while the user is active. Idle (no input > IDLE_S) stops
capture entirely. Dedupe: near-identical consecutive OCR for the same window
emits once (Jaccard >= DEDUP_JACCARD), so a static screen never floods the
store.

Start (needs Screen Recording permission for the invoking terminal — macOS
prompts on first capture; without it OCR comes back near-empty and the daemon
says so):
    nohup .venv/bin/python scripts/mac_screen_daemon.py >> /tmp/trace_screen.log 2>&1 &
Stop:
    pkill -f mac_screen_daemon.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HUB = "http://127.0.0.1:8765/capture/perception"
BLOCKLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "privacy_blocklist.json"
# FRAME GOLD (founder order 2026-07-06: no authored batteries — they bias; the
# frame IS the ground truth). Every SAMPLE window, ONE screenshot survives
# deletion into evaluation/frame_gold/ with a sidecar (t, app, url, windows).
# Eval derives questions FROM the frame, blind to the store. Local-only,
# gitignored, privacy-blocklist rows are never sampled, purgeable anytime.
FRAME_GOLD_DIR = Path(__file__).resolve().parent.parent / "evaluation" / "frame_gold"
FRAME_GOLD_EVERY_S = 300.0
POLL_S = 2.0
CAPTURE_S = 5.0
IDLE_S = 120.0
DEDUP_JACCARD = 0.9
MAX_TEXT = 900
EXCLUDE_APPS = {"TRACE"}
EXCLUDE_TITLE_MARKERS = ("TRACE —", "TRACE -")


# ---------------------------------------------------------------- pure logic

def load_blocklist(path: Path = BLOCKLIST_PATH) -> list:
    try:
        return [m.lower() for m in json.loads(path.read_text())["markers"] if m.strip()]
    except Exception:
        return []


def is_private(text: str, markers: list) -> bool:
    """Privacy censor (founder order 2026-07-05): if ANY marker appears in the
    OCR text or window title, the ENTIRE capture is dropped — no row, no focus
    event, an honest gap. Case-insensitive substring; list lives in
    config/privacy_blocklist.json."""
    lowered = text.lower()
    return any(m in lowered for m in markers)


def normalized_tokens(text: str) -> set:
    return {t for t in "".join(
        c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 1}


def should_emit(prev_text: str | None, new_text: str) -> bool:
    """Dedupe owner: emit iff the OCR meaningfully changed since the last emit
    for this same (app, window). Pure — unit-tested without TCC."""
    if not new_text.strip():
        return False
    if prev_text is None:
        return True
    a, b = normalized_tokens(prev_text), normalized_tokens(new_text)
    if not a and not b:
        return False
    union = a | b
    jaccard = len(a & b) / len(union) if union else 1.0
    return jaccard < DEDUP_JACCARD


def excluded(app: str, title: str) -> bool:
    if app in EXCLUDE_APPS:
        return True
    return any(m in title for m in EXCLUDE_TITLE_MARKERS)


def region_of(rx: float, ry: float) -> str:
    """Screen-region banding within a window (relative coords, origin top-left).
    The founder's Rao-Bahadur lesson (2026-07-05): a text bag can't tell the
    PLAYING video from a TAB TITLE of another site. Region is the cheapest
    structural fact that separates them: tab strips and toolbars live in the
    top band, queues and recommendations in the right rail, navigation in the
    left rail — the thing you're actually watching/reading is in MAIN."""
    if ry < 0.10:
        return "top-chrome"
    if ry > 0.92:
        return "bottom-chrome"
    if rx < 0.20:
        return "left-rail"
    if rx > 0.76:
        return "right-rail"
    return "main"


def attribute_spans(spans: list, windows: list) -> list:
    """(text, cx, cy) in screen points + window rects (z-order, front first)
    -> (text, window_index_or_None, region). Pure — unit-tested."""
    out = []
    for text, cx, cy in spans:
        placed = False
        for i, w in enumerate(windows):
            if w["x"] <= cx <= w["x"] + w["w"] and w["y"] <= cy <= w["y"] + w["h"]:
                rx = (cx - w["x"]) / max(w["w"], 1.0)
                ry = (cy - w["y"]) / max(w["h"], 1.0)
                out.append((text, i, region_of(rx, ry)))
                placed = True
                break
        if not placed:
            out.append((text, None, "desktop"))
    return out


def format_screen_text(app: str, title: str, lines: list) -> str:
    joined = " ; ".join(lines)
    if len(joined) > MAX_TEXT:
        joined = joined[:MAX_TEXT].rstrip() + "…"
    return f"SCREEN | app={app} window={title[:80]} | text: {joined}"


# ------------------------------------------------------------- macOS senses

def frontmost() -> tuple:
    """(app_name, window_title, windows) where windows = layer-0 rects in
    z-order (front first): {app, title, x, y, w, h, front}. Titles/bounds of
    other apps need the same Screen Recording permission the capture needs."""
    from AppKit import NSWorkspace
    import Quartz

    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    name = str(app.localizedName()) if app else "?"
    pid = int(app.processIdentifier()) if app else -1
    title = ""
    windows: list = []
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements, Quartz.kCGNullWindowID) or []
    for w in info:
        if int(w.get("kCGWindowLayer", 1)) != 0:
            continue
        b = w.get("kCGWindowBounds") or {}
        is_front = int(w.get("kCGWindowOwnerPID", -2)) == pid
        if is_front and not title:
            title = str(w.get("kCGWindowName") or "")
        windows.append({
            "app": str(w.get("kCGWindowOwnerName") or "?"),
            "title": str(w.get("kCGWindowName") or ""),
            "x": float(b.get("X", 0)), "y": float(b.get("Y", 0)),
            "w": float(b.get("Width", 0)), "h": float(b.get("Height", 0)),
            "front": is_front,
        })
    return name, title, windows, pid


BROWSER_URL_SCRIPTS = {
    "Brave Browser": 'tell application "Brave Browser" to get URL of active tab of front window',
    "Google Chrome": 'tell application "Google Chrome" to get URL of active tab of front window',
    "Safari": 'tell application "Safari" to get URL of current tab of front window',
}


def active_tab_url(app: str) -> str | None:
    """The browser's own truth about WHAT SITE the front tab is — OCR can never
    recover this (a tab title from another site reads identically to a video
    title). Needs one-time Automation (TCC) approval per browser."""
    script = BROWSER_URL_SCRIPTS.get(app)
    if not script:
        return None
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
        url = r.stdout.strip()
        return url[:120] if r.returncode == 0 and url.startswith("http") else None
    except Exception:
        return None


def idle_seconds() -> float:
    import Quartz
    return float(Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType))


def finalize_frame_gold(candidate: Path, *, app: str, title: str,
                        url: str | None, windows: list, ocr_joined: str,
                        blocklist: list) -> bool:
    """Candidate frame -> gold (or oblivion). The privacy check runs AFTER OCR,
    so the frame is held as a candidate and only finalized when clean; private
    candidates are unlinked, keeping L1's spirit: only chosen gold survives."""
    probe = " ".join([title or "", url or "", ocr_joined])
    if is_private(probe, blocklist):
        candidate.unlink(missing_ok=True)
        return False
    FRAME_GOLD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    dest = FRAME_GOLD_DIR / f"frame-{stamp}.png"
    candidate.rename(dest)
    sidecar = {
        "t_ms": stamp, "app": app, "window": title, "url": url,
        "windows": [{k: w.get(k) for k in ("app", "title", "front")} for w in windows],
    }
    (FRAME_GOLD_DIR / f"frame-{stamp}.json").write_text(json.dumps(sidecar))
    return True


def capture_and_ocr(tmp_dir: Path, keep_copy: Path | None = None) -> list:
    """screencapture (main display) -> Vision OCR WITH GEOMETRY -> DELETE the
    png (L1). keep_copy: frame-gold candidate path — copied before deletion,
    finalized or unlinked by the caller after the privacy check.
    Returns (text, cx, cy) span centers in SCREEN POINTS, top-left origin."""
    png = tmp_dir / f"scr-{int(time.time()*1000)}.png"
    try:
        r = subprocess.run(["screencapture", "-x", "-m", "-t", "png", str(png)],
                           capture_output=True, timeout=15)
        if r.returncode != 0 or not png.exists():
            return []
        if keep_copy is not None:
            import shutil
            shutil.copy2(png, keep_copy)
        import Quartz
        import Vision
        from Foundation import NSURL

        screen = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        sw, sh = float(screen.size.width), float(screen.size.height)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            NSURL.fileURLWithPath_(str(png)), None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(1)  # accurate — screen text is small
        req.setUsesLanguageCorrection_(True)
        handler.performRequests_error_([req], None)
        spans = []
        for obs in req.results() or []:
            cand = obs.topCandidates_(1)
            if cand and cand[0].confidence() >= 0.4:
                txt = str(cand[0].string()).strip()
                if len(txt) >= 2:
                    bb = obs.boundingBox()  # normalized, origin BOTTOM-left
                    cx = (bb.origin.x + bb.size.width / 2) * sw
                    cy = (1.0 - (bb.origin.y + bb.size.height / 2)) * sh
                    spans.append((txt, cx, cy))
        return spans
    finally:
        png.unlink(missing_ok=True)  # the pixels die HERE, every path


def post(text: str, helper_id: str, provenance: dict, session_id: str) -> bool:
    obs = {
        "contract": 1, "helper_id": helper_id, "text": text,
        "t_ms": int(time.time() * 1000), "confidence": 0.85,
        "session_id": session_id, "provenance": provenance,
    }
    req = urllib.request.Request(HUB, data=json.dumps(obs).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False  # hub away — drop this tick, the next one retries


# --------------------------------------------------------------------- loop

def main() -> int:
    session = datetime.now().strftime("mac-screen-%Y%m%d")
    tmp_dir = Path(tempfile.mkdtemp(prefix="trace-screen-"))
    blocklist = load_blocklist()
    print(f"[screen-daemon] privacy blocklist: {len(blocklist)} markers", flush=True)
    # P34 Stage A: the AX channel (semantic, grade=authoritative). Trust may be
    # granted mid-run — recheck periodically instead of requiring a restart.
    import ax_adapter
    ax_ok = ax_adapter.ax_trusted()
    ax_recheck_at = 0.0
    ax_enabled_pids: set = set()
    last_ax: dict = {}
    print(f"[screen-daemon] AX channel: {'ON' if ax_ok else 'off (no Accessibility trust yet)'}",
          flush=True)
    last_focus = None
    last_capture_t = 0.0
    last_gold_t = 0.0
    last_emitted: dict = {}  # (app,title) -> last emitted OCR text
    empty_streak = 0
    print(f"[screen-daemon] up — session={session} hub={HUB}", flush=True)

    while True:
        time.sleep(POLL_S)
        if idle_seconds() > IDLE_S:
            continue
        app, title, windows, pid = frontmost()
        if excluded(app, title):
            continue
        focus_changed = (app, title) != last_focus
        if focus_changed:
            last_focus = (app, title)
            if is_private(title, blocklist):
                continue  # private window: no focus row either — honest gap
            post(f"SCREEN | focus | {app} — {title[:120]}", "mac_app_focus",
                 {"app": app, "window": title, "event": "focus"}, session)
        if not focus_changed and time.time() - last_capture_t < CAPTURE_S:
            continue
        last_capture_t = time.time()
        gold_candidate = None
        if time.time() - last_gold_t >= FRAME_GOLD_EVERY_S:
            gold_candidate = tmp_dir / "gold-candidate.png"
        spans = capture_and_ocr(tmp_dir, keep_copy=gold_candidate)
        if not spans:
            empty_streak += 1
            if empty_streak == 5:
                print("[screen-daemon] 5 empty OCRs — grant Screen Recording "
                      "permission to this terminal (System Settings → Privacy)",
                      flush=True)
            continue
        empty_streak = 0
        url = active_tab_url(app)
        if gold_candidate is not None and gold_candidate.exists():
            ocr_joined = " ; ".join(t for t, _, _ in spans)
            if finalize_frame_gold(gold_candidate, app=app, title=title, url=url,
                                   windows=windows, ocr_joined=ocr_joined,
                                   blocklist=blocklist):
                last_gold_t = time.time()
                print("[screen-daemon] frame-gold saved", flush=True)
            else:
                last_gold_t = time.time()  # private moment: skip this window
        if url and is_private(url, blocklist):
            continue  # private site: drop the whole capture
        # AX channel — the OS's own semantics, emitted alongside OCR (which
        # remains the fallback for what AX can't see: video frames, canvases).
        if not ax_ok and time.time() > ax_recheck_at:
            ax_ok = ax_adapter.ax_trusted()
            ax_recheck_at = time.time() + 60
            if ax_ok:
                print("[screen-daemon] AX trust granted — semantic channel ON", flush=True)
        if ax_ok:
            try:
                if pid not in ax_enabled_pids:
                    ax_adapter.enable_web_ax(pid)
                    ax_enabled_pids.add(pid)
                els = ax_adapter.walk_front_window(pid)
                ax_rows = ax_adapter.elements_to_rows(app, url, els)
                joined = " ; ".join(r["text"] for r in ax_rows)
                if joined and not is_private(joined, blocklist) \
                        and should_emit(last_ax.get((app, url)), joined):
                    posted = sum(
                        1 for r in ax_rows
                        if post(r["text"], "mac_ax", r["provenance"], session))
                    last_ax[(app, url)] = joined
                    print(f"[screen-daemon] AX emitted {app}: {posted} elements"
                          f"{' url' if url else ''}", flush=True)
            except Exception as exc:  # noqa: BLE001 — AX flakiness never kills capture
                print(f"[screen-daemon] AX walk failed: {exc}", flush=True)
        # Attribute every span to its window + region; emit the FRONT window's
        # spans grouped per region — the relations (playing vs tab-strip vs
        # queue) survive into the store instead of dying in a text bag.
        front_idx = next((i for i, w in enumerate(windows) if w["front"]), None)
        attributed = attribute_spans(spans, windows)
        by_region: dict = {}
        for text_span, widx, region in attributed:
            if widx == front_idx and widx is not None:
                by_region.setdefault(region, []).append(text_span)
        url_tag = f" | url={url}" if url else ""
        for region, lines in sorted(by_region.items()):
            body = " ; ".join(lines)
            if len(body) > MAX_TEXT:
                body = body[:MAX_TEXT].rstrip() + "…"
            text = f"SCREEN | app={app}{url_tag} | region={region} | text: {body}"
            if is_private(text, blocklist):
                continue
            key = (app, title, region)
            if should_emit(last_emitted.get(key), text):
                if post(text, "mac_screen_ocr",
                        {"app": app, "window": title, "url": url,
                         "region": region, "display": "main"}, session):
                    last_emitted[key] = text
                    print(f"[screen-daemon] emitted {app}/{region} "
                          f"({len(lines)} spans){' url' if url else ''}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
