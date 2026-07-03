# P20 — Mac screen daemon (the digital pillar)
wave: W2 · tag: guided · executor: Opus effort=medium · depends: P02

## Context (self-contained)
Half the founder's waking day is a computer screen; the memory is blind to it. Build the
Mac-side standing helper: periodically capture the Mac's OWN screen (ScreenCaptureKit),
OCR it (Vision — native screenshot OCR is proven; it was camera-films-screen that failed),
plus focused-app + window-title tracking, and post observations through the P02 contract
to the hub (`scripts/trace_hub.py`, :8765). An old design existed pre-greenfield
(`screen_capture_daemon.py`, deleted); this is a fresh build against the contract.

## Laws that bind you
L1: the Mac's screen pixels are captured ON the Mac and DELETED after OCR — only text +
metadata persist (same frames-die rule as the phone). L5: no app-specific content parsing
in this packet (that's dispatched-specialist territory, W3+). Privacy: exclude the TRACE
app's own windows to avoid feedback loops.

## Do
1. `scripts/mac_screen_daemon.py` (or Swift if ScreenCaptureKit demands it — executor
   documents the call): adaptive cadence (on window-focus change + every ~5s while the
   screen changes; idle detection stops capture), screenshot → Vision OCR → structured
   observation: `helper_id=mac_screen_ocr`, text = OCR spans, provenance = {app, window
   title, display}; frontmost-app changes are their own observations (`mac_app_focus`).
2. Dedupe: consecutive near-identical OCR (same window, ~same text) emits once —
   the store must not drown in static-screen repeats.
3. Runbook line: how the founder starts/stops it (launchd is TCC-hostile per past
   experience — userland keepalive).
4. TCC: screen-recording permission flow documented for the founder.

## Done when
A 30-minute real work session lands as observations (apps, window titles, readable text);
"what was the error I saw in the terminal?"-class questions answer through /ask on the
resulting store; repeats deduped (measured rows/minute sane); pytest + battery hold.
INDEX flipped.
