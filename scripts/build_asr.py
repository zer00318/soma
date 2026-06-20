#!/usr/bin/env python3
"""Speech channel — local on-device ASR (mlx-whisper, M2 Metal).

The walk clip was near-silent so a transcript was never load-bearing; the
"Day in life" clip is the opposite — spoken names ("Joe", "April"), a lecturer's
name, a greeting ("Whatsup?") are the GROUND TRUTH for several questions, and the
old audio_events.json only flags *non-speech energy*. This adds the actual words.

The wav is read ONCE here (the no-raw-storage contract: audio is turned to text and
the wav is never reopened at query time). Output:
  - <memory>/asr.json     : {model, language, duration_s, full_text, segments[]}
  - <memory>/transcript.txt: human/timestamped, consumed by ask_home's voice channel

Run:  .venv/bin/python scripts/build_asr.py --audio <wav> --out-dir <memory>
      [--model mlx-community/whisper-large-v3-turbo]
All local. First run downloads the model from HF once, then offline.
"""
from __future__ import annotations
import argparse, json, os, sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="path to audio .wav")
    ap.add_argument("--out-dir", required=True, help="memory dir to write asr.json + transcript.txt")
    ap.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    ap.add_argument("--language", default=None, help="force a language code, else auto-detect")
    args = ap.parse_args()

    import mlx_whisper
    import numpy as np
    import soundfile as sf

    # mlx_whisper.load_audio() shells out to ffmpeg even for a .wav; we have no ffmpeg.
    # Decode the wav ourselves (soundfile) and hand transcribe() a float32 mono 16k array.
    data, sr = sf.read(args.audio, always_2d=False)
    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)
    data = np.asarray(data, dtype=np.float32)
    if sr != 16000:
        n = int(round(len(data) * 16000 / sr))
        data = np.interp(np.linspace(0, len(data), n, endpoint=False),
                         np.arange(len(data)), data).astype(np.float32)

    kw = dict(path_or_hf_repo=args.model, word_timestamps=False)
    if args.language:
        kw["language"] = args.language
    print(f"[asr] transcribing {args.audio} with {args.model} ...", flush=True)
    res = mlx_whisper.transcribe(data, **kw)

    segs = [{"start": round(s.get("start", 0.0), 2),
             "end": round(s.get("end", 0.0), 2),
             "text": (s.get("text") or "").strip()}
            for s in res.get("segments", []) if (s.get("text") or "").strip()]
    full = (res.get("text") or "").strip()
    out = {
        "model": args.model,
        "language": res.get("language", args.language or ""),
        "duration_s": round(segs[-1]["end"], 1) if segs else 0.0,
        "full_text": full,
        "segments": segs,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    ap_json = os.path.join(args.out_dir, "asr.json")
    json.dump(out, open(ap_json, "w"), ensure_ascii=False, indent=2)

    # transcript.txt: timestamped lines, plus a header the voice specialist can read.
    lines = ["# voice channel: ON-DEVICE ASR (%s), lang=%s, %d segments" %
             (args.model.split("/")[-1], out["language"], len(segs))]
    for s in segs:
        lines.append("[%6.1f-%6.1fs] %s" % (s["start"], s["end"], s["text"]))
    open(os.path.join(args.out_dir, "transcript.txt"), "w").write("\n".join(lines) + "\n")

    print(f"[asr] {len(segs)} segments, {len(full)} chars -> {ap_json}", flush=True)
    if full:
        print("[asr] preview:", full[:400], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
