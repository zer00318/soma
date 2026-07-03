# P13 — The look-again loop (active perception)
wave: W1 · tag: guided · executor: Opus effort=medium · depends: P12

## Context (self-contained)
Founder's requirement: "a live search engine that gathers more information whenever it
requires, automatically — a bit of brain in the live portions." Perception must notice its
own gaps and re-ask, on-device, in the moment: object confirmed but unlabeled → zoomed
crop re-read; text detected but low-confidence OCR → full-res re-OCR of that region;
fingerprint missing on a confirmed track → schedule one. The crop-zoom machinery exists
(M5's EnrichmentScheduler in `trace-native-fastvlm/FastVLM App/` — throttled, with a kill
switch because it once froze the app); this packet turns it from a fixed schedule into a
gap-driven one.

## Laws that bind you
L1 (everything on-device). Respect the existing throttle + kill-switch patterns — the app
freezing mid-capture is a demo-killing failure mode we already paid for once.

## Do
1. Gap detector on the live binder's output: rank open gaps (unlabeled instance > unread
   text > missing fingerprint), budgeted (max N re-asks/minute, drop stale gaps when the
   camera moved on).
2. Route each gap to the right re-ask: crop→VLM, region→OCR, crop→fingerprint. Results
   flow through the normal contract (helper_id marks them as look-again passes).
3. Instrument: per-session counts of gaps found/closed — the Leash's coverage numbers
   should visibly improve on a cluttered-desk capture.

## Done when
On a real cluttered capture, ≥50% of detected gaps close within the session; app survives
20 minutes of capture with the loop on (no freeze, kill switch works); pytest + battery
hold; iOS build green. INDEX flipped with the gaps-found/closed numbers.
