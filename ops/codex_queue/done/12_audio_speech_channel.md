# CODEX BRIEF 12 — audio/speech channel (brain side): "what was said / what did I hear"

Branch: `codex/12-audio`. Python via `.venv/bin/python`. Additive. Do NOT touch `trace-native-fastvlm/`
or `src/trace_memory/domain/`. Builds on `live_eventlog.py`.

## Why
The app already emits `EVENT | nearby speech | transcript: "..."` records (and will add more audio later).
The event-log path must ingest speech as observations and answer "what was said / what did I hear / did
someone mention X". (App-side Whisper is separate; this is the brain side that makes audio answerable.)

## Tasks
1. In `append_perception_observations`, parse `EVENT | nearby speech | transcript: "<text>"` (and any
   `kind=event subject=speech`) into an Observation with `kind="speech"`, subject="speech",
   attribute value = the transcript, source_channel="audio".
2. In `answer_question`, add a SPEECH intent ("what was said", "what did I hear", "did anyone mention X",
   "who said what"): answer from speech observations (quote the transcript with its time). For "did someone
   mention X" → yes/no grounded in whether X appears in a speech transcript; refuse if no speech captured.
3. Honest default: if no speech observations exist, refuse ("I didn't capture any speech").

## Acceptance (`tests/test_audio_speech.py`)
- Append a speech observation transcript "let's grab coffee at noon", then:
  - "what was said" → quotes it (with time).
  - "did anyone mention coffee" → yes, grounded.
  - "did anyone mention pizza" → no / honest.
  - no speech in memory → "what was said" refuses.

## Guardrails
- Additive; `pytest tests/ -q` passes. No domain edits. Commit on branch. Report example answers.
