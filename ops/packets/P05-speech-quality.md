# P05 — Speech quality: whole utterances, not shreds
wave: W0 · tag: guided · executor: Opus effort=medium (Swift + Python) · depends: none
status: READY

## Context (self-contained — founder complaint 2026-07-04: "the transcribed text is very bad")
The ASR channel is structurally ALIVE (fixed 2026-07-04: audio-session activation) but
what it WRITES is shredded. Real rows from the founder's morning walk
(data/trace_store.sqlite3, ~08:26–08:28):
  "Everything I" · "do I do I do it just for you for you" · "You're my only" ·
  "This is my bathroom" · "You have your towels you" · "a beautiful mirror that you can
  absolve me" · "You have a washing machine I guess it's 1 to 8 cases"
Three distinct problems:
1. **Fragmentation (the big one).** `commitIfUseful` in
   `trace-native-fastvlm/FastVLM App/TraceLiveContextEngines.swift` commits a DELTA every
   ≥5 s of continuous speech — arbitrary mid-sentence slices become separate memories.
   A narration becomes 6 shreds; retrieval then surfaces one shred without its sentence.
2. **Mis-transcription.** "absolve me" (likely "observe yourself"), "1 to 8 cases"
   (likely "1 to 8 kg" — it's a washing machine). SFSpeechRecognizer is the OLD engine;
   iOS 26 ships SpeechAnalyzer/SpeechTranscriber — Apple's long-form on-device engine,
   substantially better on continuous narration. The phone is iPhone 17 / iOS 26.
3. **Music vs speech.** Bryan Adams lyrics ("Everything I do…") captured as 'nearby
   speech' twice. Not wrong (it WAS nearby audio) but should eventually be tagged as
   music (P23's SoundAnalysis classifier is the cross-check; note the hook, don't build it).

## Laws that bind you
L1 (all on-device; verbatim text only leaves). L2 (verbatim is sacred — never "clean up"
words the engine actually produced; stitching may only JOIN fragments, not rewrite them).
Respect the M5 lesson: cumulative-partial duplication was already fixed once — keep the
delta-baseline logic intact for whatever cadence you choose.

## Do
1. **Utterance-boundary commits (Swift).** Replace the fixed 5s slice with natural
   endpoints: commit on `result.isFinal` OR on a detected pause (no new partial for
   ~1.2s) — whichever comes first. A continuous sentence lands as ONE memory row with a
   t_ms span. Keep a hard ceiling (~20s) so a monologue still commits progressively.
2. **Engine upgrade spike (Swift, timeboxed half-day).** Swap SFSpeechRecognizer for iOS
   26 SpeechAnalyzer/SpeechTranscriber in `TraceAudioContextEngine`; measure on the same
   spoken script (founder reads ~10 sentences): word-error impression + fragment count
   vs old engine, numbers into this file. Keep SFSpeech as fallback behind a flag.
3. **Sleep-side stitcher (Python).** In the sleep pass, adjacent speech rows (<3s gap,
   same session) merge into an authored utterance memory citing the fragments —
   retroactively heals ALL existing shredded capture, not just future ones.
4. Regression tests for the stitcher (fixture with shredded rows → one authored
   utterance, verbatim preserved, citations intact).

## Done when
A founder narration lands as sentence-shaped rows (or is healed at sleep); old walks'
fragments stitch into readable utterances; "what did I say about the washing machine"
through live /ask returns a coherent sentence; pytest + battery hold. INDEX flipped with
the engine-spike numbers.

## Executed (2026-07-04, Opus)
1. **Utterance-boundary commits — SHIPPED.** `commitIfUseful`'s fixed 5s cadence is gone.
   `handleRecognition` now routes each SFSpeech result: `isFinal` commits the whole utterance
   as one row; volatile partials feed `onPartial`, which (re)arms a `pauseCommitTask` that
   commits after `pausePartialSeconds = 1.2` of no new partial (a detected pause), with a
   `hardCeilingSeconds = 20` fallback so a monologue still commits progressively. The M5
   cumulative-delta baseline (`cumulativeCommitted`) is preserved — the boundary logic only
   changes WHEN we commit, not the dedup of what. Tail is flushed on error teardown so words
   aren't lost. `stop()` cancels the pause task.
2. **Engine spike — SHIPPED BEHIND FLAG** (`static let useSpeechAnalyzerEngine = false`).
   `startAnalyzerEngine()` (`@available(iOS 26.0, *)`) wires the iOS 26 long-form on-device
   engine: `SpeechTranscriber(locale:preset:.progressiveTranscription)` + `SpeechAnalyzer`,
   mic buffers streamed via `AsyncStream<AnalyzerInput>`, results routed through the SAME
   utterance-boundary commit path (final vs volatile). SFSpeech stays the fallback (flag off).
   Compiles against the iOS 26.2 SDK (verified BUILD SUCCEEDED in the main checkout — the
   isolated worktree has a clean-derived-data `FastVLM` module-scan flake that also fails the
   UNMODIFIED baseline, so it is not caused by this change). **WER / fragment-count numbers are
   DEVICE-PENDING** — they require the founder to flip the flag, read the ~10-sentence script on
   the iPhone 17, and compare against SFSpeech. Numbers go here when measured (founder-session
   gate). No AVAudioSession or M5 logic was disturbed.
3. **Sleep-side stitcher — SHIPPED** (`SleepConsolidator._stitch_speech`, `src/trace_memory/
   store/sleep.py`). Adjacent raw speech rows (helper in {asr, apple_speech, native_speech,
   speech} or text 'EVENT | nearby speech'), same session, gap < 3s, join into ONE authored
   `event_memory` (`EVENT | speech utterance | transcript: "..."`) citing every fragment via
   `supports_memory`. Verbatim only concatenated in time order (L2), never rewritten; raw rows
   never touched (L3); authored under builder=sleep so `reconsider_derived` heals idempotently.
4. **Tests — GREEN.** `tests/unit/test_speech_stitcher.py` (7 cases): adjacent fragments →
   one utterance, wide-gap → separate, citations intact + raw untouched + still immutable,
   single fragment not authored, reconsolidation idempotent, different sessions don't merge.
   Full suite: 263 passed + 7 new = 270 green.
