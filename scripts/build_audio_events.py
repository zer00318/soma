#!/usr/bin/env python3
"""SOMA capture-time audio-event detector (RELATIVE / adaptive).

WHY THIS WAS REWRITTEN
----------------------
The previous detector used an ABSOLUTE silence gate: if the whole file sat
below -45 dB it returned usable_sound=false with ZERO events and refused. On
this walk that gate fired (overall -47.6 dB) and the detector therefore MISSED
a child who audibly yelled near the end. The recording is genuinely muffled,
but the yell is still THERE as a RELATIVE spike: ~-44 dB at t~89s and again at
t~76s, riding ~6 dB above a ~-50 dB local floor. A single global threshold can
never see that — the signal is loud *relative to its surroundings*, not loud in
absolute terms.

So detection is now ADAPTIVE. For each short window we compute its energy in dB
and compare it to a LOCAL rolling-median baseline (and the local MAD). A window
is flagged as an event when it rises significantly above its own neighbourhood
(default >= +4 dB over the rolling median AND >= 4x the local MAD), regardless
of the absolute level. This makes the detector honest in BOTH directions: it
finds the quiet-but-real yell, and on a truly flat recording (no relative
excursions) it still produces no events.

`usable_sound` no longer means "absolute level above a floor". It now means
"this capture contains at least one above-baseline acoustic event worth
reporting". A near-silent file with a real spike is usable; a near-silent file
with nothing rising above its own noise is not.

ON-DEVICE CLASSIFICATION (best effort)
--------------------------------------
When Apple's SoundAnalysis framework is importable (pyobjc-framework-
SoundAnalysis) and its file analyzer succeeds, each flagged event is enriched
with the top on-device class label (e.g. crying_sobbing, children_shouting,
screaming, yell). That classifier is run in an ISOLATED SUBPROCESS so that any
instability in the native analyzer can never crash this detector. If the
framework is missing, or the analyzer fails on this OS build (it returns a
generic "Code=2" on some Ventura configs), we DEGRADE GRACEFULLY: the event is
still reported, labelled from acoustic shape as "loud vocalization/unidentified"
(or impact/alarm-like where the spectrum clearly says so). We never drop a real
event just because the fancy classifier was unavailable.

NO-RAW-STORAGE CONTRACT
-----------------------
The wav is opened ONCE here, summarised to a tiny JSON (audio_events.json), and
never re-read at query time. ask_home.py answers sound questions from that JSON
alone.

Per-window features (numpy + soundfile only):
  - RMS energy in dB              (vs a LOCAL rolling-median baseline + MAD)
  - zero-crossing rate            (voiced vs noisy)
  - spectral centroid (Hz)
  - low/mid/high band ratios      (0-500 / 500-2000 / 2000+ Hz)

Output JSON schema (consumed by ask_home.load_audio_events / answer_audio_events):
  {
    "overall_db": float,
    "usable_sound": bool,          # >=1 above-baseline event found
    "duration_s": float,
    "frame_s": float, "hop_s": float,
    "baseline_db": float,          # median of the per-window dB curve
    "rel_gate_db": float,          # the relative gate used
    "classifier": str,             # "apple_soundanalysis" | "acoustic_heuristic"
    "events": [
      {start, end, label, confidence, evidence,
       peak_db, baseline_db, delta_db, apple_label(optional)}
    ]
  }

CLI:
  python scripts/build_audio_events.py --audio path/to/audio.wav \
      --out path/to/audio_events.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf


# ──────────────────────────────────────────────────────────────────────────────
# Tuneable thresholds
# ──────────────────────────────────────────────────────────────────────────────
REL_GATE_DB     = 4.0     # window must rise >= this many dB over the LOCAL median
REL_GATE_MADS   = 4.0     # ...AND >= this many local MADs (robust z-score)
BASELINE_WIN_S  = 10.0    # length of the rolling-baseline window (seconds)
MIN_MAD_DB      = 0.5     # floor on MAD so a dead-flat region can't divide by ~0
ABS_FALLBACK_DB = -25.0   # an absolutely loud window is always an event too

# Frame geometry. 1 s frames @ 0.5 s hop gives ~2 Hz time resolution, enough to
# localise a yell to a couple of seconds while keeping the FFT bins meaningful.
FRAME_S = 1.0
HOP_S   = 0.5

PITCH_MIN_HZ = 60.0
PITCH_MAX_HZ = 1000.0


# ──────────────────────────────────────────────────────────────────────────────
# DSP helpers
# ──────────────────────────────────────────────────────────────────────────────
def _rms_db(x: np.ndarray) -> float:
    return 20.0 * math.log10(math.sqrt(float(np.mean(x ** 2))) + 1e-10)


def _zcr(x: np.ndarray) -> float:
    if len(x) < 2:
        return 0.0
    s = np.sign(x)
    s[s == 0] = 1
    return float(np.count_nonzero(np.diff(s))) / (len(x) - 1)


def _rolling_median(x: np.ndarray, k: int) -> np.ndarray:
    """Edge-padded rolling median; same length as x."""
    if k < 1:
        return x.copy()
    if k % 2 == 0:
        k += 1
    half = k // 2
    pad = np.pad(x, (half, half), mode="edge")
    return np.array([np.median(pad[i:i + k]) for i in range(len(x))])


def _band_ratios(mag: np.ndarray, freqs: np.ndarray) -> Tuple[float, float, float, float]:
    tot = float(np.sum(mag))
    if tot <= 1e-10:
        return 0.0, 0.0, 0.0, 0.0
    centroid = float(np.sum(freqs * mag) / tot)
    low = float(np.sum(mag[freqs <= 500]) / tot)
    mid = float(np.sum(mag[(freqs > 500) & (freqs <= 2000)]) / tot)
    high = float(np.sum(mag[freqs > 2000]) / tot)
    return centroid, low, mid, high


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 2)


# ──────────────────────────────────────────────────────────────────────────────
# Acoustic-shape labelling (the always-available fallback)
# ──────────────────────────────────────────────────────────────────────────────
def _shape_label(delta_db: float, zcr: float, centroid: float,
                 low: float, mid: float, high: float) -> Tuple[str, str]:
    """Label an above-baseline event from spectral shape alone.

    Returns (label, evidence). The relative spike has ALREADY qualified this as
    an event; here we only describe what kind of sound it acoustically resembles.
    We deliberately stay conservative: a voiced, mid/high-energy excursion is a
    "loud vocalization/unidentified" (it could be a yell or a cry — we do not
    claim which without the on-device classifier), a low-frequency thump is an
    "impact/thump-like", a bright wideband burst is "alarm/whistle-like".
    """
    ev = (f"+{delta_db:.1f}dB over local floor, centroid={centroid:.0f}Hz, "
          f"zcr={zcr:.2f}, mid+high={mid + high:.2f}")

    # Bright, wideband, hissy -> alarm/whistle/siren family.
    if centroid > 2500 and high > 0.45:
        return "alarm/whistle-like", ev
    # Low-frequency dominated, low ZCR -> a thump/door/impact.
    if low > 0.55 and zcr < 0.10 and centroid < 800:
        return "impact/thump-like", ev
    # Mid/high voiced energy -> a vocalization (yell/cry/shout), but unidentified
    # without the classifier. This is the bucket the walk's child yell lands in.
    if (mid + high) > 0.45:
        return "loud vocalization/unidentified", ev
    # Otherwise a generic salient excursion.
    return "loud sound/unidentified", ev


# ──────────────────────────────────────────────────────────────────────────────
# Apple SoundAnalysis (best-effort, isolated subprocess)
# ──────────────────────────────────────────────────────────────────────────────
def _apple_available() -> bool:
    try:
        import SoundAnalysis  # noqa: F401
        import Foundation     # noqa: F401
        return True
    except Exception:
        return False


# Classes the on-device classifier may emit that we care about, mapped to a
# human label for the event log. Anything else is reported as "sound:<id>".
_APPLE_RELEVANT = {
    "crying_sobbing": "crying",
    "baby_crying": "baby crying",
    "children_shouting": "children shouting/yelling",
    "screaming": "screaming",
    "yell": "yelling",
    "shout": "shouting",
    "battle_cry": "yelling",
    "child_speech": "child speech",
    "baby_laughter": "baby laughter",
    "laughter": "laughter",
    "speech": "speech",
    "crowd": "crowd",
    "siren": "siren",
    "police_siren": "siren",
    "ambulance_siren": "siren",
    "fire_engine_siren": "siren",
}


def _run_apple_subprocess(wav_path: str, timeout: float = 60.0) -> Optional[List[Dict[str, Any]]]:
    """Run the SoundAnalysis classifier on wav_path in a SEPARATE python process.

    Isolation is deliberate: the native analyzer is known to be unstable under
    pyobjc on some macOS builds (it can return "Code=2" or, in async run-loop
    mode, even segfault). Running it out-of-process means the WORST case is a
    non-zero exit we ignore — this detector keeps running and falls back to the
    acoustic-shape labels. Returns a list of {start, end, label, confidence} or
    None if the classifier was unavailable / failed.
    """
    import subprocess

    helper = (
        "import sys, json, math\n"
        "try:\n"
        "    import SoundAnalysis as SA\n"
        "    import Foundation, objc\n"
        "    import soundfile as sf, numpy as np, tempfile, os\n"
        "except Exception as e:\n"
        "    print('UNAVAILABLE:'+str(e)); sys.exit(0)\n"
        "wav=sys.argv[1]\n"
        "# Re-encode to 44.1k mono PCM16 (the v1 classifier's native rate).\n"
        "data,sr=sf.read(wav, always_2d=False)\n"
        "if getattr(data,'ndim',1)>1: data=data.mean(axis=1)\n"
        "data=np.asarray(data, dtype=np.float32)\n"
        "if sr!=44100:\n"
        "    n=int(len(data)*44100/sr)\n"
        "    if n>1:\n"
        "        xi=np.linspace(0,len(data)-1,n)\n"
        "        data=np.interp(xi,np.arange(len(data)),data).astype(np.float32)\n"
        "    sr=44100\n"
        "tmp=os.path.join(tempfile.gettempdir(),'soma_sa_%d.wav'%os.getpid())\n"
        "sf.write(tmp,data,sr,subtype='PCM_16')\n"
        "req,err=SA.SNClassifySoundRequest.alloc().initWithClassifierIdentifier_error_(SA.SNClassifierIdentifierVersion1,None)\n"
        "if req is None:\n"
        "    print('UNAVAILABLE:request_init'); sys.exit(0)\n"
        "def cmsecs(t):\n"
        "    try: return float(t.value)/float(t.timescale) if t.timescale else 0.0\n"
        "    except Exception: return 0.0\n"
        "rows=[]; state={'done':False,'err':None}\n"
        "class Obs(Foundation.NSObject):\n"
        "    def request_didProduceResult_(self, request, result):\n"
        "        cls=result.classifications(); tr=result.timeRange()\n"
        "        if cls and len(cls):\n"
        "            c0=cls[0]\n"
        "            rows.append({'start':cmsecs(tr.start),'dur':cmsecs(tr.duration),\n"
        "                         'id':str(c0.identifier()),'conf':float(c0.confidence())})\n"
        "    def request_didFailWithError_(self, request, error):\n"
        "        state['err']=str(error); state['done']=True\n"
        "    def requestDidComplete_(self, request):\n"
        "        state['done']=True\n"
        "url=Foundation.NSURL.fileURLWithPath_(tmp)\n"
        "analyzer,e2=SA.SNAudioFileAnalyzer.alloc().initWithURL_error_(url,None)\n"
        "if analyzer is None:\n"
        "    print('UNAVAILABLE:analyzer_init'); sys.exit(0)\n"
        "obs=Obs.alloc().init()\n"
        "ok,e3=analyzer.addRequest_withObserver_error_(req,obs,None)\n"
        "analyzer.analyze()\n"
        "try: os.unlink(tmp)\n"
        "except Exception: pass\n"
        "if state['err'] and not rows:\n"
        "    print('FAILED:'+state['err']); sys.exit(0)\n"
        "print('OK:'+json.dumps(rows))\n"
    )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        helper_path = f.name
        f.write(helper)
    try:
        proc = subprocess.run(
            [sys.executable, helper_path, wav_path],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception:
        return None
    finally:
        try:
            os.unlink(helper_path)
        except Exception:
            pass

    out = (proc.stdout or "").strip()
    if not out or not out.startswith("OK:"):
        return None
    try:
        raw = json.loads(out[len("OK:"):])
    except Exception:
        return None

    results: List[Dict[str, Any]] = []
    for r in raw:
        start = float(r.get("start", 0.0))
        dur = float(r.get("dur", 0.0))
        results.append({
            "start": start,
            "end": start + dur,
            "id": str(r.get("id", "")),
            "confidence": float(r.get("conf", 0.0)),
        })
    return results


def _apple_label_for_span(apple_results: List[Dict[str, Any]],
                          start: float, end: float) -> Optional[Tuple[str, str, float]]:
    """Pick the strongest relevant Apple classification overlapping [start,end].

    Returns (human_label, raw_id, confidence) or None.
    """
    best = None
    for r in apple_results:
        # overlap test with a small tolerance window
        if r["end"] < start - 1.0 or r["start"] > end + 1.0:
            continue
        rid = r["id"]
        if rid not in _APPLE_RELEVANT:
            continue
        if best is None or r["confidence"] > best["confidence"]:
            best = r
    if best is None:
        return None
    return _APPLE_RELEVANT[best["id"]], best["id"], best["confidence"]


# ──────────────────────────────────────────────────────────────────────────────
# Core detection
# ──────────────────────────────────────────────────────────────────────────────
def detect(audio_path: str, frame_s: float = FRAME_S, hop_s: float = HOP_S,
           use_apple: bool = True) -> Dict[str, Any]:
    """Read the wav ONCE and return the adaptive event log dict.

    Detection is relative: a window is an event if its dB rises >= REL_GATE_DB
    over the local rolling-median baseline AND >= REL_GATE_MADS local MADs (or it
    is absolutely loud, > ABS_FALLBACK_DB). usable_sound = at least one event.
    """
    data, sr = sf.read(audio_path, always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float64)

    overall_db = _rms_db(data)
    duration_s = len(data) / sr if sr else 0.0

    frame_len = max(1, int(frame_s * sr))
    hop_len = max(1, int(hop_s * sr))

    result: Dict[str, Any] = {
        "overall_db": round(overall_db, 2),
        "usable_sound": False,
        "duration_s": round(duration_s, 2),
        "frame_s": frame_s,
        "hop_s": hop_s,
        "baseline_db": None,
        "rel_gate_db": REL_GATE_DB,
        "classifier": "acoustic_heuristic",
        "events": [],
    }

    if len(data) < frame_len:
        return result

    win_fn = np.hanning(frame_len)
    freqs = np.fft.rfftfreq(frame_len, 1.0 / sr)

    starts: List[int] = []
    dbs: List[float] = []
    feats: List[Tuple[float, float, float, float, float]] = []  # zcr, centroid, low, mid, high
    for start in range(0, len(data) - frame_len + 1, hop_len):
        win = data[start:start + frame_len]
        db = _rms_db(win)
        mag = np.abs(np.fft.rfft(win * win_fn))
        centroid, low, mid, high = _band_ratios(mag, freqs)
        zcr = _zcr(win)
        starts.append(start)
        dbs.append(db)
        feats.append((zcr, centroid, low, mid, high))

    dbs_arr = np.asarray(dbs)
    result["baseline_db"] = round(float(np.median(dbs_arr)), 2)

    # Local rolling baseline + robust scale (MAD).
    win_frames = max(3, int(round(BASELINE_WIN_S / hop_s)))
    baseline = _rolling_median(dbs_arr, win_frames)
    mad = _rolling_median(np.abs(dbs_arr - baseline), win_frames)
    mad = np.maximum(mad, MIN_MAD_DB)
    delta = dbs_arr - baseline

    flagged = (((delta >= REL_GATE_DB) & (delta >= REL_GATE_MADS * mad))
               | (dbs_arr >= ABS_FALLBACK_DB))

    # Build per-frame candidate events (shape-labelled).
    frames: List[Dict[str, Any]] = []
    for i, is_flag in enumerate(flagged):
        if not is_flag:
            continue
        zcr, centroid, low, mid, high = feats[i]
        label, evidence = _shape_label(float(delta[i]), zcr, centroid, low, mid, high)
        # Confidence scales with how far above the local floor and how many MADs.
        z = float(delta[i]) / float(mad[i])
        conf = _clamp(0.25 + 0.10 * (float(delta[i]) - REL_GATE_DB) + 0.05 * (z - REL_GATE_MADS))
        frames.append({
            "start": starts[i] / sr,
            "end": (starts[i] + frame_len) / sr,
            "label": label,
            "confidence": conf,
            "evidence": evidence,
            "peak_db": round(float(dbs_arr[i]), 2),
            "baseline_db": round(float(baseline[i]), 2),
            "delta_db": round(float(delta[i]), 2),
        })

    # Merge adjacent flagged frames (any labels) into single events; the label of
    # the merged event is the loudest constituent frame's label.
    merged: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for fr in frames:
        if cur is not None and fr["start"] <= cur["end"] + (hop_s + 1e-6):
            cur["end"] = max(cur["end"], fr["end"])
            cur["_frames"].append(fr)
        else:
            if cur is not None:
                merged.append(cur)
            cur = {"start": fr["start"], "end": fr["end"], "_frames": [fr]}
    if cur is not None:
        merged.append(cur)

    # Optional on-device classification (best effort, isolated subprocess).
    apple_results: Optional[List[Dict[str, Any]]] = None
    if use_apple and merged and _apple_available():
        apple_results = _run_apple_subprocess(audio_path)
        if apple_results is not None:
            result["classifier"] = "apple_soundanalysis"

    events: List[Dict[str, Any]] = []
    for m in merged:
        fl = m["_frames"]
        peak = max(fl, key=lambda f: f["peak_db"])
        event = {
            "start": round(m["start"], 2),
            "end": round(m["end"], 2),
            "label": peak["label"],
            "confidence": round(float(np.mean([f["confidence"] for f in fl])), 2),
            "evidence": peak["evidence"],
            "peak_db": peak["peak_db"],
            "baseline_db": peak["baseline_db"],
            "delta_db": peak["delta_db"],
        }
        # Enrich with the Apple class if one overlaps this span.
        if apple_results is not None:
            hit = _apple_label_for_span(apple_results, m["start"], m["end"])
            if hit is not None:
                human, raw_id, aconf = hit
                event["apple_label"] = raw_id
                event["label"] = human
                event["evidence"] = (event["evidence"]
                                     + f"; apple={raw_id} ({aconf:.0%})")
                event["confidence"] = round(max(event["confidence"], aconf), 2)
        events.append(event)

    result["events"] = events
    result["usable_sound"] = bool(events)
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="SOMA capture-time audio-event detector (relative/adaptive)")
    ap.add_argument("--audio", type=str, default="", help="Path to audio .wav")
    ap.add_argument("--out", type=str, default="", help="Output audio_events.json path")
    ap.add_argument("--frame", type=float, default=FRAME_S, help="Window length (seconds)")
    ap.add_argument("--hop", type=float, default=HOP_S, help="Window hop (seconds)")
    ap.add_argument("--no-apple", action="store_true",
                    help="Skip the Apple SoundAnalysis enrichment pass")
    args = ap.parse_args()

    if not args.audio:
        ap.error("--audio is required")

    result = detect(args.audio, frame_s=args.frame, hop_s=args.hop,
                    use_apple=not args.no_apple)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)

    print("=" * 60)
    print("SOMA audio-event detector (relative/adaptive)")
    print("=" * 60)
    print(f"  audio        : {args.audio}")
    print(f"  duration     : {result['duration_s']}s")
    print(f"  overall level: {result['overall_db']} dB")
    print(f"  baseline     : {result['baseline_db']} dB (median window energy)")
    print(f"  rel gate     : +{result['rel_gate_db']} dB over local median")
    print(f"  classifier   : {result['classifier']}")
    print(f"  usable_sound : {result['usable_sound']}")
    print(f"  events       : {len(result['events'])}")
    for e in result["events"]:
        ap_lbl = (" apple=%s" % e["apple_label"]) if "apple_label" in e else ""
        print(f"    [{e['start']:6.2f}s-{e['end']:6.2f}s] {e['label']:<32} "
              f"(conf {e['confidence']:.2f}) peak={e['peak_db']}dB "
              f"d=+{e['delta_db']}dB{ap_lbl}")
    if not result["events"]:
        print("    (no above-baseline events — capture is acoustically flat)")
    if args.out:
        print(f"  wrote        : {args.out}")


if __name__ == "__main__":
    main()
