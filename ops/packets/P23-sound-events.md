# P23 — Ambient sound events (the non-speech ear)
wave: W2 · tag: guided · executor: Sonnet or Opus effort=medium · depends: P02

## Context (self-contained)
The mic already runs for ASR, but non-speech sound is discarded: doorbells, alarms,
kettle whistling, music playing, a dog, glass breaking. Apple's SoundAnalysis framework
(SNClassifySoundRequest, ~300 built-in classes) classifies on-device on the same audio
tap. Note an old pre-greenfield experiment existed (`scripts/audio_events.py`,
`build_audio_events.py`) — reference only; the build is fresh, Swift-side, through the
P02 contract.

## Laws that bind you
L1: audio never leaves the phone; only event labels + confidence + timestamps do. L5.
Do not degrade ASR — the sound tap must coexist with the speech pipeline.

## Do
1. Swift: SoundAnalysis on the existing audio stream during capture; emit observations on
   event onset above a confidence floor (`helper_id=sound_event`, text "sound: doorbell",
   dedupe sustained sounds into one event with duration, e.g. "music playing, ~12 min").
2. Class filter: keep the ~30 life-relevant classes (doorbell, alarm, knock, dog, cat,
   music, water running, vehicle, laughter, crying, cough, phone ringing, etc. — list in
   one constants block, documented; this is a structural allowlist of SNClassifier class
   ids, not a content lexicon over user data).
3. Rate control: a noisy café must not flood the store (measured rows/minute cap).
4. Seam test through real Hub.ingest; iOS build green.

## Done when
A real capture with a planted doorbell/alarm/music lands correct labeled events;
"did music play this afternoon" answers through /ask; flood test sane; pytest + battery
hold. INDEX flipped.
