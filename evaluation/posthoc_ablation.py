#!/usr/bin/env python3
"""Post-Hoc Answerability Ablation — the experiment that decides Trace's thesis.

The thesis ("Context -> Prompt -> Answer") is only true if the on-device
pixel->text derivation preserves the answer to questions nobody had asked yet.
This measures exactly that, per frame, with everything local (ollama gemma3):

  1. DERIVE   the text Trace would KEEP  = perception prompt on the pixel.
  2. GENERATE post-hoc questions FROM THE PIXEL (+ gold answers) — i.e. questions
     a user might ask later, that were NOT known at capture time.
  3. ANSWER FROM TEXT   — the brain, given ONLY the derived text (raw discarded).
  4. ANSWER FROM PIXEL  — the oracle / upper bound (a competitor who KEEPS pixels).
  5. JUDGE each answer vs gold -> CORRECT / WRONG / REFUSED.

Headline metrics (the kill-gate numbers):
  answerable_from_text = CORRECT / valid          (>= 0.40 to keep the thesis)
  hallucination_rate   = WRONG / (CORRECT+WRONG)  (<  0.10 to keep the thesis)
A question is "valid" only if the pixel-oracle itself answered it correctly
(otherwise it was a bad/ambiguous question, not a memory failure).

No raw media is read by the brain step — only the derived text. The pixel is
used solely to (a) generate the questions and (b) establish the oracle ceiling,
mirroring "what a pixel-keeping competitor could still answer."
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# Exact production perception prompt (kept in sync with scripts/trace_live_feed.py).
PERCEIVE_PROMPT = (
    "You are a person's first-person camera walking through the world. Report ONLY "
    "what is actually visible in THIS frame — never guess or carry over. Output exactly:\n"
    "SCENE: <one short sentence>\n"
    "OBJECTS: <comma-separated concrete things you actually see>\n"
    "TEXT: <any on-screen/sign text copied verbatim, or NONE>\n"
    "PEOPLE: <count and what they appear to be doing, or NONE>"
)

QGEN_PROMPT = (
    "You are building a fair memory test. Look ONLY at this single first-person photo. "
    "Write {k} specific, factual, closed questions whose answers are CLEARLY VISIBLE in "
    "THIS photo, each with its correct short answer from the photo. Prefer concrete visible "
    "facts: colours, counts, readable sign/store text, object presence, what people are doing. "
    "No yes/no questions, nothing needing outside knowledge or another photo. "
    'Return STRICT JSON only: [{{"q":"...","gold":"..."}}]'
)

ANSWER_FROM_TEXT_PROMPT = (
    "You are Trace's memory. The original image was DISCARDED; you have ONLY this derived "
    "text record of the moment:\n---\n{derived}\n---\n"
    "Answer the question using ONLY facts present in the text above. If the answer is not "
    "clearly in the text, reply EXACTLY: NOT IN MEMORY. Never guess. One short sentence.\n"
    "Question: {q}"
)

ANSWER_FROM_PIXEL_PROMPT = "Answer this question about the image concisely and factually, in one short sentence.\nQuestion: {q}"

JUDGE_PROMPT = (
    'Grade a memory answer. Gold truth (from the original image): "{gold}"\n'
    'Candidate answer: "{cand}"\n'
    "Rules: if the candidate says it does not know / NOT IN MEMORY / refuses -> REFUSED. "
    "Else if its factual content matches the gold answer -> CORRECT. Else -> WRONG. "
    "Output ONLY one word: CORRECT, WRONG, or REFUSED."
)


def ollama(model: str, prompt: str, images: list[str] | None, host: str, timeout: int = 240) -> str:
    payload: dict = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if images:
        payload["images"] = images
    data = json.dumps(payload).encode()
    req = urllib.request.Request(host + "/api/generate", data=data, headers={"Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read()).get("response", "").strip()
        except Exception as exc:  # one retry, then surface
            if attempt == 1:
                raise
            time.sleep(2)
    return ""


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def parse_qjson(raw: str, k: int) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for item in arr[:k]:
        if isinstance(item, dict) and item.get("q") and item.get("gold"):
            out.append({"q": str(item["q"]).strip(), "gold": str(item["gold"]).strip()})
    return out


def judge(model: str, gold: str, cand: str, host: str) -> str:
    v = ollama(model, JUDGE_PROMPT.format(gold=gold, cand=cand), None, host).upper()
    if "REFUS" in v or "NOT IN MEMORY" in v:
        return "REFUSED"
    if "CORRECT" in v:
        return "CORRECT"
    if "WRONG" in v:
        return "WRONG"
    return "WRONG"  # unparseable judge defaults to the conservative (counts against us)


def sample_frames(frames_dir: Path, n: int) -> list[Path]:
    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        sys.exit(f"no frames in {frames_dir}")
    if n >= len(frames):
        return frames
    step = len(frames) / n
    return [frames[int(i * step)] for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-dir", default="data/walks/walk_outside_20260614/work/run_frames")
    ap.add_argument("--n", type=int, default=6, help="frames to sample")
    ap.add_argument("--k", type=int, default=2, help="post-hoc questions per frame")
    ap.add_argument("--derive-model", default="gemma3:12b-it-qat")
    ap.add_argument("--oracle-model", default="gemma3:12b-it-qat")
    ap.add_argument("--judge-model", default="gemma3:12b-it-qat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--out", default="evaluation/ras/posthoc_ablation.json")
    args = ap.parse_args()

    frames = sample_frames(Path(args.frames_dir), args.n)
    rows: list[dict] = []
    t_start = time.time()
    for fi, fp in enumerate(frames):
        img = b64(fp)
        derived = ollama(args.derive_model, PERCEIVE_PROMPT, [img], args.host)
        qs = parse_qjson(ollama(args.oracle_model, QGEN_PROMPT.format(k=args.k), [img], args.host), args.k)
        for q in qs:
            text_ans = ollama(args.derive_model, ANSWER_FROM_TEXT_PROMPT.format(derived=derived, q=q["q"]), None, args.host)
            pixel_ans = ollama(args.oracle_model, ANSWER_FROM_PIXEL_PROMPT.format(q=q["q"]), [img], args.host)
            v_text = judge(args.judge_model, q["gold"], text_ans, args.host)
            v_pixel = judge(args.judge_model, q["gold"], pixel_ans, args.host)
            rows.append({
                "frame": fp.name, "question": q["q"], "gold": q["gold"],
                "derived_text": derived, "text_answer": text_ans, "pixel_answer": pixel_ans,
                "verdict_text": v_text, "verdict_pixel": v_pixel,
                "valid": v_pixel == "CORRECT",  # oracle could answer => fair question
            })
        print(f"  frame {fi+1}/{len(frames)} {fp.name}: {len(qs)} q  ({time.time()-t_start:.0f}s)", file=sys.stderr, flush=True)

    valid = [r for r in rows if r["valid"]]
    nvalid = len(valid)
    correct = sum(r["verdict_text"] == "CORRECT" for r in valid)
    wrong = sum(r["verdict_text"] == "WRONG" for r in valid)
    refused = sum(r["verdict_text"] == "REFUSED" for r in valid)
    answered = correct + wrong
    summary = {
        "frames": len(frames), "questions_total": len(rows), "questions_valid": nvalid,
        "pixel_ceiling": round(nvalid / len(rows), 3) if rows else 0.0,
        "answerable_from_text": round(correct / nvalid, 3) if nvalid else 0.0,
        "hallucination_rate": round(wrong / answered, 3) if answered else 0.0,
        "refusal_rate": round(refused / nvalid, 3) if nvalid else 0.0,
        "counts": {"correct": correct, "wrong": wrong, "refused": refused},
        "models": {"derive": args.derive_model, "oracle": args.oracle_model, "judge": args.judge_model},
        "frames_dir": args.frames_dir, "elapsed_s": round(time.time() - t_start, 1),
        "kill_gate": {"answerable_from_text>=0.40": (correct / nvalid if nvalid else 0) >= 0.40,
                      "hallucination_rate<0.10": (wrong / answered if answered else 1) < 0.10},
    }
    out = {"summary": summary, "rows": rows}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
