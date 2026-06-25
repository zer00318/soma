# FOUNDER DESK TEST 2 — spatial permanence (run morning of Jun 12)

A FRESH build went onto your iPhone at 01:28 tonight. Important finding:
**last night's failed test ran a STALE build** — the phone was posting
`native_vision_classifier` words (art/decoration/jewelry garbage), a code
path that doesn't even exist in the repo anymore. So the MobileCLIP path
has never actually been device-tested. This is its first real test.
The lifecycle bugs you hit (everything gone after kill) were real and are
fixed in the build now installed.

Total time: ~6 minutes. Do the steps in order; the order is the test.

## 0. Identity check (30s) — never skip again

Open the app → Spatial mode. The status line MUST say
`MobileCLIP S0 ready (82 words)` somewhere in it. If it says anything
about FastVLM scanner or shows no MobileCLIP text → STOP, write "stale
build" to the reply file (step 6); don't bother testing.

## 1. Naming + pinning (2 min)

Stand at your desk. Pan slowly across cpu, fan, keyboard, mouse, monitor,
bottle — dwell ~2s on each. Watch the word map.
- PASS bar: ≥4 of those objects appear as the RIGHT word, roughly where
  the object is.
- Note (mentally) any object that gets a WRONG word and any that never
  gets named.

## 2. Duplicate check (1 min)

Pick one named object (e.g. bottle). Look away 5s, pan back to it, dwell
again. Repeat twice.
- PASS: still ONE word for it on the map (sightings go up, no second
  copy).

## 3. The kill test (1 min)

Swipe-kill the app (app switcher, swipe up). Wait 10s. Reopen → Spatial
mode. Pan the desk once.
- PASS: your words come back (loaded from disk), placed where they were.
  It may say "waiting relocalization" briefly — that's correct behavior.

## 4. Dashboard check (1 min)

On the mac, open http://localhost:8777/world — your desk words should be
there. (If the page says "waiting for phone spatial snapshot", note it —
that's a known gap Codex is fixing today: the dashboard only shows the
latest post, not stored state. Not your build's fault.)

## 5. Leave the evidence

Plug the phone in, leave it UNLOCKED for a minute. I pull
`spatial_diag.ndjson` off the device myself — every naming decision is
logged; I tune thresholds from this data, not from impressions.

## 6. Report (one line is enough)

`echo "step1 PASS/FAIL, step2 PASS/FAIL, step3 PASS/FAIL, step4 yes/no, notes: ..." > /tmp/trace_founder_reply.txt`

Honest misses are worth more than polite passes — wrong words and
never-named objects are exactly what grows the vocabulary tomorrow.
