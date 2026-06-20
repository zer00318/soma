#!/usr/bin/env python3
"""SOMA Audio-Event Specialist — non-speech sound event detector.

This module is the "hearing" channel of the SOMA specialist society.
Whisper covers speech-to-text; this module handles everything Whisper
cannot: crying, yelling, bangs, alarms, music, crowd noise, etc.

DETECTION IS RELATIVE / ADAPTIVE
--------------------------------
This module no longer uses an absolute energy gate. A muffled recording can
still contain a real event (a child who yelled near the end of an otherwise
near-silent walk shows up as a ~+6 dB spike over a ~-50 dB local floor, never
crossing any absolute -35 dB threshold). So detection delegates to
build_audio_events.detect(), which flags a window when it rises significantly
above its LOCAL rolling-median baseline. The heavy lifting (relative gate,
acoustic-shape labels, optional on-device Apple SoundAnalysis classification)
lives in build_audio_events.py; this module is the query-time wrapper around it.

Implementation: numpy + soundfile only (no librosa / torchaudio), plus an
optional best-effort Apple SoundAnalysis pass when the framework is present.

ENTRYPOINTS:
  detect_events(audio_path) -> list[{start, end, label, confidence, ...}]
  answer(question, audio_path, model, host, timeout) -> str

CLI:
  python scripts/audio_events.py --self-test
  python scripts/audio_events.py --audio path/to/audio.wav
  python scripts/audio_events.py --question "was there a child crying?" \\
      --audio path/to/audio.wav
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
import urllib.error
from typing import List, Dict, Any

import numpy as np
import soundfile as sf

# The relative/adaptive detector lives in build_audio_events.py (same dir). We
# delegate detection to it so there is ONE detector, not two that disagree.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_audio_events as _bae  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Tuneable constants
# ──────────────────────────────────────────────────────────────────────────────

FRAME_SECONDS  = 0.5          # analysis frame length
HOP_SECONDS    = 0.25         # frame hop (50 % overlap)
MIN_SILENCE_DB = -50.0        # frames below this dB are ignored entirely
ENERGY_DB_THR  = -35.0        # louder than this → candidate event
MERGE_GAP_S    = 0.5          # merge adjacent events closer than this
MIN_EVENT_S    = 0.2          # drop events shorter than this after merge

# ZCR / centroid boundaries (empirically set from walk data exploration)
ZCR_LOW    = 0.08
ZCR_HIGH   = 0.18
CENT_LOW   = 800    # Hz
CENT_HIGH  = 2000   # Hz

# Keywords that map to audio-event category questions
CRYING_KEYWORDS   = {"cry", "crying", "cried", "sob", "sobbing", "scream",
                      "screaming", "yell", "yelling", "yelled", "wail",
                      "wailing", "child", "kid", "baby"}
SPEECH_KEYWORDS   = {"talk", "talking", "said", "spoke", "speaking", "voice",
                      "speech", "words", "word"}
MUSIC_KEYWORDS    = {"music", "song", "singing", "playing"}
ALARM_KEYWORDS    = {"alarm", "siren", "beep", "horn", "announcement",
                      "announcement"}
NOISE_KEYWORDS    = {"noise", "loud", "sound", "hear", "heard", "audio"}


# ──────────────────────────────────────────────────────────────────────────────
# Core DSP helpers
# ──────────────────────────────────────────────────────────────────────────────

def _rms_db(samples: np.ndarray) -> float:
    rms = math.sqrt(float(np.mean(samples ** 2)) + 1e-30)
    return 20.0 * math.log10(rms)


def _zcr(samples: np.ndarray) -> float:
    """Zero-crossing rate (crossings per sample)."""
    if len(samples) < 2:
        return 0.0
    signs = np.sign(samples)
    signs[signs == 0] = 1          # treat zero as positive
    crossings = np.sum(np.diff(signs) != 0)
    return float(crossings) / (len(samples) - 1)


def _spectral_centroid(samples: np.ndarray, sr: int) -> float:
    """Spectral centroid in Hz using real FFT."""
    mag = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sr)
    total = float(np.sum(mag))
    if total < 1e-12:
        return 0.0
    return float(np.sum(freqs * mag) / total)


def _tag_frame(db: float, zcr: float, centroid: float) -> tuple[str, float]:
    """Return (label, confidence) for a single loud frame."""
    if db < ENERGY_DB_THR:
        return "ambient", 0.0

    # crude rule-based taxonomy
    if zcr < ZCR_LOW and centroid < CENT_LOW:
        return "thud_or_bass_event", 0.60
    if ZCR_LOW <= zcr < ZCR_HIGH and centroid < CENT_HIGH:
        # could be voice / shout; mid-range ZCR + mid centroid
        return "voice_or_yell_like", 0.55
    if zcr >= ZCR_HIGH and centroid >= CENT_HIGH:
        return "scream_or_alarm_like", 0.65
    if zcr >= ZCR_HIGH:
        return "noise_burst", 0.50
    return "unclassified_loud_event", 0.40


# ──────────────────────────────────────────────────────────────────────────────
# Public API: detect_events
# ──────────────────────────────────────────────────────────────────────────────

def detect_events(audio_path: str, use_apple: bool = True) -> List[Dict[str, Any]]:
    """Return a list of detected non-speech sound events (RELATIVE detector).

    Delegates to build_audio_events.detect(), which flags windows that rise
    above their LOCAL rolling-median baseline (so a quiet-but-real yell in a
    muffled recording is found, where an absolute gate would miss it). Each
    event carries {start, end, label, confidence, evidence, peak_db,
    baseline_db, delta_db} and, when the on-device classifier succeeds,
    apple_label. An empty list means no above-baseline event was found.
    """
    log = _bae.detect(audio_path, use_apple=use_apple)
    return list(log.get("events") or [])


# ──────────────────────────────────────────────────────────────────────────────
# Gemma call helper
# ──────────────────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, model: str, host: str, timeout: int) -> str:
    payload = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as exc:
        return f"[ollama error: {exc}]"


# ──────────────────────────────────────────────────────────────────────────────
# Public API: answer
# ──────────────────────────────────────────────────────────────────────────────

def answer(
    question:   str,
    audio_path: str,
    model:      str  = "gemma3:12b-it-qat",
    host:       str  = "http://127.0.0.1:11434",
    timeout:    int  = 30,
) -> str:
    """Answer an audio-event question from the captured audio.

    Runs detect_events() on audio_path, then decides whether the question
    is about crying/yelling, speech, music, alarms, or general noise and
    gives an honest answer.  If the audio is silent / uneventful, refuses
    to invent events.
    """
    q_lower = question.lower()
    q_words = set(q_lower.split())

    # Detect what we can
    events = detect_events(audio_path)

    # Compute overall stats for refusal context
    try:
        data, sr = sf.read(audio_path, always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        global_db = _rms_db(data.astype(np.float64))
    except Exception:
        global_db = -99.0

    # "Silent" no longer means a low ABSOLUTE level — a muffled recording can
    # still hold a real event. The honest signal is whether any window rose above
    # its LOCAL baseline, i.e. whether detect_events() returned anything.
    is_quiet_overall = global_db < -42.0   # our walk is -47.6 dB overall

    # Classify intent
    wants_crying = bool(q_words & CRYING_KEYWORDS)
    wants_speech = bool(q_words & SPEECH_KEYWORDS)
    wants_music  = bool(q_words & MUSIC_KEYWORDS)
    wants_alarm  = bool(q_words & ALARM_KEYWORDS)
    wants_any    = bool(q_words & NOISE_KEYWORDS) or not (
                       wants_crying or wants_speech or wants_music or wants_alarm)

    # Events that could be a cry/yell: anything with a vocal-ish label. The
    # relative detector tags voiced excursions "loud vocalization/unidentified";
    # the Apple classifier (when available) upgrades them to crying/yelling/
    # children-shouting/screaming. Match all of those.
    _CRY_HINTS = ("yell", "scream", "cry", "crying", "shout", "vocal",
                  "child", "baby")
    cry_events = [e for e in events
                  if any(h in str(e.get("label", "")).lower() for h in _CRY_HINTS)]

    # ── Crying / yelling question ──────────────────────────────────────────
    if wants_crying:
        if not cry_events:
            return (
                "No child crying or yelling was detected. The captured audio held "
                f"no above-baseline vocal events (overall level {global_db:.1f} dB; "
                "no window rose far enough over its local floor to register as a "
                "cry or yell)."
            )
        parts = []
        identified = False
        for e in cry_events:
            lbl = str(e.get("label", ""))
            if "unidentified" not in lbl:
                identified = True
            parts.append(
                f"{lbl} from {e['start']:.1f}s–{e['end']:.1f}s "
                f"(conf {e['confidence']:.0%}, +{e.get('delta_db', 0):.1f} dB over "
                "local floor)"
            )
        lead = ("A child crying/yelling was detected" if identified
                else "Loud vocal sound(s) were detected (a likely cry or yell, "
                     "though too muffled for the on-device classifier to name)")
        tail = ("." if identified else
                ". The recording is muffled, so this is the acoustic shape, not a "
                "named class — verify with human review.")
        return lead + ": " + "; ".join(parts) + tail

    # ── General query — let gemma reason over the event list ───────────────
    if events:
        event_summary = json.dumps(events, indent=2)
    else:
        event_summary = "No above-baseline non-speech events detected."

    audible = "near-silent overall but with above-baseline events" if (is_quiet_overall and events) \
        else ("near-silent" if is_quiet_overall else "audible")
    db_note = f"Overall audio level: {global_db:.1f} dB ({audible})."

    prompt = f"""You are the audio-event specialist for a wearable perception system.
You have run a frame-level energy / zero-crossing / spectral analysis on the captured audio.

Audio summary:
{db_note}
Detected events (JSON):
{event_summary}

The user's question: "{question}"

Rules:
1. If no relevant events were detected and the audio is near-silent, say so honestly.
   Do NOT invent sounds.
2. If events were detected, cite their timestamps and labels.
3. Keep the answer concise (2-4 sentences).

Answer:"""

    return _call_ollama(prompt, model, host, timeout)


# ──────────────────────────────────────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────────────────────────────────────

WALK_AUDIO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "walks", "walk_outside_20260614", "memory", "audio.wav"
)


def _self_test() -> bool:
    ok = True

    print("=" * 60)
    print("SELF-TEST: audio_events.py")
    print("=" * 60)

    # ── Test 1: Real walk → finds the muffled yell near the end ────────────
    # The founder confirmed a child audibly yelled near the END. It is a
    # RELATIVE spike (~-44 dB at t~89s over a ~-50 dB floor), so the adaptive
    # detector MUST find at least one event whose span includes ~89s. A miss
    # here is the exact bug this rewrite closes.
    print("\n[1] detect_events on real walk audio (expect a relative spike ~89s) …")
    audio = os.path.realpath(WALK_AUDIO)
    if not os.path.exists(audio):
        print(f"  SKIP (audio not found at {audio})")
    else:
        events = detect_events(audio)
        print(f"  Events found: {len(events)}")
        for e in events:
            print(f"    {e}")
        near_89 = [e for e in events
                   if e["start"] - 1.5 <= 89.0 <= e["end"] + 1.5]
        if near_89:
            print("  PASS — relative detector found the muffled vocal spike near "
                  f"t~89s: {[(e['start'], e['end'], e['label']) for e in near_89]}")
        else:
            print("  FAIL — no event near t~89s; the child yell was missed")
            ok = False

    # ── Test 2: Synthesised loud burst → detector fires ────────────────────
    print("\n[2] detect_events on synthesised 0.5 s loud burst …")
    sr_synth = 16000
    silence = np.zeros(int(2.0 * sr_synth))           # 2 s silence
    burst   = np.random.randn(int(0.5 * sr_synth)) * 0.4  # -8 dB burst
    signal  = np.concatenate([silence, burst, silence])

    import tempfile, wave, struct
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    sf.write(tmp_path, signal, sr_synth)

    burst_events = detect_events(tmp_path)
    os.unlink(tmp_path)
    print(f"  Events found: {len(burst_events)}")
    for e in burst_events:
        print(f"    {e}")
    if burst_events:
        # Check burst is centred around 2-2.5 s
        centres = [(e["start"] + e["end"]) / 2 for e in burst_events]
        near_burst = any(1.5 <= c <= 3.0 for c in centres)
        if near_burst:
            print("  PASS — burst detected at the right time")
        else:
            print(f"  WARN — burst not centred around 2.5 s: {centres}")
            ok = False
    else:
        print("  FAIL — no events detected for loud burst")
        ok = False

    # ── Test 3: answer() on real walk for crying question ──────────────────
    print("\n[3] answer() — 'Was there a child crying or yelling?' …")
    if os.path.exists(audio):
        ans = answer(
            "Was there a child crying or yelling?",
            audio,
            model="gemma3:12b-it-qat",
            host="http://127.0.0.1:11434",
            timeout=30,
        )
        print(f"  Answer: {ans}")
        al = ans.lower()
        # The walk DOES contain a muffled yell now, so the honest answer is the
        # opposite of before: it should AFFIRM a detected vocal event, not deny.
        if ("detect" in al and ("vocal" in al or "yell" in al or "cry" in al
                                or "child" in al or "shout" in al)) \
                and not al.startswith("no child"):
            print("  PASS — affirms the detected vocal event with a timestamp")
        else:
            print("  WARN — answer did not surface the detected vocal event; review")
            ok = False
    else:
        print("  SKIP (audio not found)")

    # ── Test 4: JSON schema output ─────────────────────────────────────────
    print("\n[4] BUILD_SCHEMA …")
    schema = {
        "specialist": "audio_events",
        "module":     "scripts/audio_events.py",
        "detector":   "scripts/build_audio_events.py (relative/adaptive)",
        "entrypoints": {
            "detect_events": "detect_events(audio_path: str) -> list[{start, end, label, confidence, evidence, peak_db, baseline_db, delta_db}]",
            "answer":        "answer(question, audio_path, model, host, timeout) -> str",
        },
        "detection":   "relative: window dB >= +4 dB over local rolling median AND >= 4 MADs",
        "features":    ["RMS_energy_dB_vs_local_baseline", "zero_crossing_rate",
                        "spectral_centroid_Hz", "low_mid_high_band_ratios"],
        "categories":  ["loud vocalization/unidentified", "loud sound/unidentified",
                        "impact/thump-like", "alarm/whistle-like",
                        "(apple) crying/yelling/children_shouting/screaming/..."],
        "on_device_classifier": "Apple SoundAnalysis (best effort, isolated subprocess; "
                                "graceful fallback to acoustic labels if unavailable)",
        "refusal_default": True,   # still refuses when NO window rises above its local floor
        "no_raw_storage":  True,
        "deps":            ["numpy", "soundfile", "pyobjc-framework-SoundAnalysis(optional)"],
    }
    print(json.dumps(schema, indent=2))
    print("\nBUILD_SCHEMA OK")

    print("\n" + ("=" * 60))
    print("OVERALL:", "PASS" if ok else "FAIL")
    print("=" * 60)
    return ok


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SOMA audio-event specialist")
    parser.add_argument("--self-test", action="store_true",
                        help="Run the self-test suite and exit")
    parser.add_argument("--audio", default=WALK_AUDIO,
                        help="Path to audio.wav")
    parser.add_argument("--question", default="",
                        help="Question to answer (uses answer() entrypoint)")
    parser.add_argument("--model",   default="gemma3:12b-it-qat")
    parser.add_argument("--host",    default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json",    action="store_true",
                        help="Print detect_events output as JSON")
    args = parser.parse_args()

    if args.self_test:
        passed = _self_test()
        sys.exit(0 if passed else 1)

    if args.question:
        result = answer(args.question, args.audio, args.model, args.host, args.timeout)
        print(result)
        return

    events = detect_events(args.audio)
    if args.json:
        print(json.dumps(events, indent=2))
    else:
        if events:
            for e in events:
                print(f"  [{e['start']:.2f}s – {e['end']:.2f}s] {e['label']} "
                      f"(conf {e['confidence']:.0%})")
        else:
            print("No salient audio events detected.")


if __name__ == "__main__":
    main()
