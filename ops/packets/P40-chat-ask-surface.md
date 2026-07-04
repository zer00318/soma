# P40 — The phone ask surface (the product loop)

wave: W4 (PULLED FORWARD by the 2026-07-04 course correction) · tag: judgment · executor: Fable/chief · depends: P02, hub /ask

## Context (self-contained)
The stocktake found the substrate strong and the product thin: the founder could only *ask*
via the Mac demo page. A phone that captures but can't be questioned on the phone is a lab,
not a product. This packet makes the phone a first-class ask surface so the daily loop —
carry → ask → cited honest answer — lives entirely on the device. Spec §: "chat app UI
(narrate → badge → receipts)."

## Laws that bind you
L1 (only text/derived leaves; no frames). The honesty moat is the point: every answer carries
a CALIBRATED badge, refusal is a feature, evidence is always shown.

## Do
1. The ask surface is a CONVERSATION, not a single-shot form: a scrolling thread of
   question→answer turns that persists in-session, auto-scrolls to the newest.
2. Each turn shows the brain's calibrated badge (firm / hedged / refused / error) + the
   confidence number, and tap-to-open RECEIPTS (when · helper · text) — the same evidence
   the demo page shows, now on the product surface.
3. Reuse the proven plumbing: `BrainClient.ask` → hub POST `/ask`. No new networking.
4. Hub: POST `/ask` carries the FULL evidence row (when/helper/text), not a flat label, so
   the phone receipts equal the demo page's.

## Forbidden
No new answer logic (the hub/agent owns answers). No inventing a "firm" badge when the hub
didn't send one (fall back to the refused flag). No frontier (allow_frontier=false).

## Done when
Reachable from a prominent entry point; a real question returns answer + calibrated badge +
expandable receipts on the phone; honest range answers stay honest (no false "firm"); iOS
build green; hub contract verified.

## Landed 2026-07-04 (code + hub contract verified; device-render pending)
- Swift (`ContentView.swift`): `askThread: [AskTurn]` replaces the flat single-answer state;
  `AskTurn`/`AskReceipt` models; `AskTurnView` renders the question bubble + badge dot +
  confidence + expandable receipts; `askSheet` is now a `ScrollViewReader` chat thread with
  a bottom input bar and empty-state starter chips. `performAsk` appends a turn and fills it
  in place. `BrainClient.AskResult` now decodes `confidence` + `badge`; `Citation` decodes
  `when`/`helper`/`text`. Reached via the existing prominent "Ask Trace" accent card. iOS
  build green.
- Hub (`scripts/trace_hub.py`): POST `/ask` citations now carry `when`/`helper`/`text`
  alongside the legacy `label` (older builds still decode). Verified live against the real
  store: "how many bottles did I see?" → "between 2 and 3", badge `hedged`, confidence 0.5,
  receipt helper `instance` + full text — the honest RANGE renders as an honest hedge, the
  moat is visible.
- DEVICE-PENDING: physical phone → Mac hub round-trip rendering the thread (same honest
  status as P10/P11 Swift when they first landed — build-verified, device-render next walk).
