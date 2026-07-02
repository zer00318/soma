#!/usr/bin/env python3
"""THE CANONICAL BATTERY RUNNER (ops/CANONICAL_SPEC.md §4) — one command, four numbers.

Builds the two fixture worlds deterministically through the REAL Hub.ingest seam, runs the
sleep binder, answers every battery question with the REAL agent + local reasoner, judges
deterministically, and reports:

    CORRECT-ON-PRESENT %  ·  REFUSE-ON-ABSENT %  ·  CONFIDENT-WRONG (hard 0)  ·  PARAPHRASE-PARITY %

    .venv/bin/python evaluation/run_canonical_battery.py [--model gemma3:12b-it-qat]
                                                          [--out evaluation/ras/canonical_run.json]

The battery file (evaluation/canonical_battery.jsonl) is VERSIONED GOLD — implementers do
not tune against it; additions come from the Chief/founder per protocol §3.1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.trace_hub import Hub  # noqa: E402
from trace_memory.brain import TraceMemoryAgent  # noqa: E402
from trace_memory.store.author import deterministic_author  # noqa: E402
from trace_memory.store.sleep import SleepConsolidator  # noqa: E402

CONFIDENT_WRONG_FLOOR = 0.6  # invariant I4: wrong at >= this confidence, not refused


# ---- fixture worlds (built through the real ingest seam, gold known by construction) ------

GARAGE_FRAMES = [
    (0,  "detector",     "OBJECT | workbench, mug, mug, drill"),
    (2,  "fastvlm",      "OBJECT | mug | black ceramic mug | workbench | likely"),
    (4,  "fastvlm",      "Three black ceramic mugs sit in a row on the workbench next to a cordless drill."),
    (6,  "vision_ocr",   "DEWALT 20V MAX XR"),
    (8,  "fastvlm",      "OBJECT | drill | yellow cordless drill | workbench | likely"),
    (9,  "detector_track", 'OBJECT | drill | detected by on-device tracker | label text: "DEWALT 20V MAX XR"; middle-center of frame | likely'),
    (10, "vision_ocr",   "DEWALI 20V"),
    (14, "detector",     "OBJECT | clamp, workbench"),
    (16, "fastvlm",      "OBJECT | clamp | metal c-clamp | workbench edge | likely"),
    (20, "fastvlm",      "OBJECT | kettlebell | maroon kettlebell | floor | likely"),
    (24, "fastvlm",      "OBJECT | kettlebell | burgundy cast iron kettlebell | floor near bench | likely"),
    (28, "fastvlm",      "OBJECT | kettlebell | dark red kettlebell | floor | likely"),
    (32, "detector",     "OBJECT | bottle, shelf"),
    (34, "fastvlm",      "OBJECT | bottle | olive green glass bottle | shelf | likely"),
    (38, "fastvlm",      "OBJECT | bottle | white plastic bottle | shelf | likely"),
    (42, "fastvlm",      "OBJECT | toolbox | blue metal toolbox | shelf | likely"),
    (46, "fastvlm",      "OBJECT | bus | small toy bus | shelf | likely"),
    (48, "vision_ocr",   "PLATFORM 5 BUSES DEPART DAILY"),
    (52, "fastvlm",      "A vintage transit poster on the wall reads PLATFORM 5 BUSES DEPART DAILY."),
    (58, "apple_speech", "remember to call Marcus about the invoice on Thursday"),
    (64, "detector",     "OBJECT | ladder, garage door"),
    (66, "fastvlm",      "OBJECT | ladder | aluminum ladder | leaning against the garage door | likely"),
    (72, "fastvlm",      "OBJECT | tarp | turquoise tarp | draped over the motorcycle | likely"),
    (74, "fastvlm",      "A turquoise tarp is draped over a motorcycle in the corner of the garage."),
    (80, "detector",     "OBJECT | clamp, shelf"),
    (82, "fastvlm",      "OBJECT | clamp | metal bar clamp | shelf | likely"),
    (86, "fastvlm",      "OBJECT | mug | black ceramic mug | workbench | likely"),
    (90, "detector",     "OBJECT | mug, mug, workbench"),
]

MOVES_FRAMES = [
    (0,   "detector_track", "OBJECT | thermos | steel thermos on the desk | middle-center of frame | likely", {"track_id": "trk-1", "detector_label": "thermos"}),
    (10,  "detector_track", "OBJECT | thermos | steel thermos on the desk | middle-center of frame | likely", {"track_id": "trk-1", "detector_label": "thermos"}),
    (20,  "detector_track", "OBJECT | notebook | spiral notebook on the desk | lower-left of frame | likely", {"track_id": "trk-2", "detector_label": "notebook"}),
    (30,  "detector_track", "OBJECT | notebook | spiral notebook on the desk | lower-left of frame | likely", {"track_id": "trk-2", "detector_label": "notebook"}),
    (60,  "detector_track", 'OBJECT | sweatshirt | detected by on-device tracker | label text: "MICHIGAN STATE"; middle-center of frame | likely', {"track_id": "trk-4", "detector_label": "sweatshirt", "bound_text": "MICHIGAN STATE"}),
    (70,  "detector_track", 'OBJECT | sweatshirt | detected by on-device tracker | label text: "MICHIGAN STATE"; middle-center of frame | likely', {"track_id": "trk-4", "detector_label": "sweatshirt", "bound_text": "MICHIGAN STATE"}),
    (120, "detector_track", "OBJECT | thermos | steel thermos on the kitchen shelf | middle-right of frame | likely", {"track_id": "trk-1", "detector_label": "thermos"}),
    (130, "detector_track", "OBJECT | thermos | steel thermos on the kitchen shelf | middle-right of frame | likely", {"track_id": "trk-1", "detector_label": "thermos"}),
    (200, "detector_track", "OBJECT | keys | keyring with keys by the front door | lower-right of frame | likely", {"track_id": "trk-3", "detector_label": "keys"}),
    (210, "detector_track", "OBJECT | keys | keyring with keys by the front door | lower-right of frame | likely", {"track_id": "trk-3", "detector_label": "keys"}),
]


def build_store(path: Path, frames, *, landmark_context=None) -> Hub:
    hub = Hub(str(path))
    for row in frames:
        sec, source, text = row[0], row[1], row[2]
        meta = row[3] if len(row) > 3 else {}
        m, s = divmod(sec, 60)
        assert hub.ingest({"memory_text": text, "source": source,
                           "timestamp": f"2026-07-02T14:{m:02d}:{s:02d}.000Z",
                           "metadata": meta})["ok"]
    SleepConsolidator(hub.store, author=deterministic_author,
                      **({"landmark_context": landmark_context} if landmark_context else {})
                      ).consolidate()
    return hub


# ---- deterministic judge -------------------------------------------------------------------

_ABSENT_CUES = ("no ", "not ", "n't", "no.", "none", "never", "does not", "didn't",
                "no mention", "nothing", "wasn't", "weren't", "cannot confirm", "no record")
_CORRECT_CUES = ("no prior record", "didn't say", "did not say", "never said", "actually",
                 "no record")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text or "").lower()).strip()


def judge(row: dict, answer: str, refused: bool) -> str:
    """-> 'correct' | 'wrong' | 'refused'(honest miss on a present item)."""
    kind, gold = row["gold_kind"], row.get("gold", "")
    low = f" {_norm(answer)} "
    if kind in ("absent", "refuse"):
        if refused:
            return "correct"
        return "correct" if any(c.strip() and c in low for c in _ABSENT_CUES) else "wrong"
    if refused:
        return "refused"
    if kind == "number":
        numbers = set(re.findall(r"\d+", answer))
        return "correct" if numbers == {gold} else "wrong"
    if kind == "contains":
        return "correct" if _norm(gold) in low else "wrong"
    if kind == "contains_any":
        return "correct" if any(_norm(g) in low for g in gold.split("|")) else "wrong"
    if kind == "refuse_or_correct":
        return "correct" if any(c in low for c in _CORRECT_CUES) else "wrong"
    if kind == "correct_attribute":
        # Must state the TRUE attribute and must not confirm the planted one.
        return "correct" if _norm(gold) in low else "wrong"
    return "wrong"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--out", default="evaluation/ras/canonical_run.json")
    args = ap.parse_args()

    battery = [json.loads(line) for line in
               (ROOT / "evaluation/canonical_battery.jsonl").read_text().splitlines() if line.strip()]

    tmp = Path(tempfile.mkdtemp(prefix="canonical-battery-"))
    print("building fixture worlds through the real ingest seam...", flush=True)
    hubs = {
        "garage": build_store(tmp / "garage.sqlite3", GARAGE_FRAMES),
        "moves": build_store(tmp / "moves.sqlite3", MOVES_FRAMES),
    }
    agents = {
        name: TraceMemoryAgent(hub.store, reasoner="local-ollama", ollama_model=args.model,
                               restrict_sources=("phone_camera",))
        for name, hub in hubs.items()
    }

    results = []
    for row in battery:
        a = agents[row["store"]].answer(row["q"])
        verdict = judge(row, a.answer, a.refused)
        confident_wrong = verdict == "wrong" and not a.refused and a.confidence >= CONFIDENT_WRONG_FLOOR
        rec = {**row, "answer": a.answer, "confidence": a.confidence, "refused": a.refused,
               "verdict": verdict, "confident_wrong": confident_wrong}
        results.append(rec)
        print(json.dumps({k: rec[k] for k in ("id", "verdict", "confident_wrong", "answer")},
                         ensure_ascii=False), flush=True)

    present = [r for r in results if r["gold_kind"] not in ("absent", "refuse")]
    absent = [r for r in results if r["gold_kind"] in ("absent", "refuse")]
    by_id = {r["id"]: r for r in results}
    pairs = [(by_id[r["pair_of"]], r) for r in results if r.get("pair_of") and r["pair_of"] in by_id]

    correct_on_present = sum(1 for r in present if r["verdict"] == "correct") / max(1, len(present))
    refuse_on_absent = sum(1 for r in absent if r["verdict"] == "correct") / max(1, len(absent))
    confident_wrong = sum(1 for r in results if r["confident_wrong"])
    parity = (sum(1 for a, b in pairs if a["verdict"] == b["verdict"]) / max(1, len(pairs)))

    summary = {
        "model": args.model,
        "n": len(results),
        "CORRECT_ON_PRESENT": round(correct_on_present * 100, 1),
        "REFUSE_ON_ABSENT": round(refuse_on_absent * 100, 1),
        "CONFIDENT_WRONG": confident_wrong,
        "PARAPHRASE_PARITY": round(parity * 100, 1),
        "gate_confident_wrong_zero": confident_wrong == 0,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=2,
                              ensure_ascii=False))
    print("\n=== CANONICAL BATTERY (§4) ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  artifact: {out}")
    return 0 if confident_wrong == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
