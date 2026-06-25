#!/usr/bin/env python3
"""Held-out eval: ask the REAL brain (ask_home.ask, anchored consensus) about a
text-rich YouTube walk the system was NEVER tuned on, and compare to founder gold.

The founder watches the video, poses a question about text they can read at ~MM:SS,
and gives their own gold answer. We run the exact shipping brain path (consensus
reads-or-refuses) anchored at that moment and log the comparison. No auto-generated
questions, no tuning corpus -> a trustworthy held-out number.

  .venv/bin/python evaluation/founder_live_eval.py --t 26:10 \
      --gold "Ludwig Beck" --model 12b "What store is on this corner?"

Logs every turn to evaluation/ras/munich_heldout_live.jsonl for tallying.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ask_home  # noqa: E402

DEFAULT_MEM = ROOT / "data" / "walks" / "munich_text" / "work" / "kf_memory.json"
LOG = ROOT / "evaluation" / "ras" / "munich_heldout_live.jsonl"
MODELS = {"12b": "gemma3:12b-it-qat", "27b": "gemma3:27b-it-qat"}


def parse_t(s: str) -> float:
    s = str(s).strip()
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(m) * 60 + float(sec)
    return float(s)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def judge(answer: str, gold: str, refused: bool) -> str:
    """Heuristic hint only — the founder is ground truth. correct/refused/wrong."""
    if refused:
        return "refused"
    a, g = _norm(answer), _norm(gold)
    if not g:
        return "?"
    gt = [t for t in g.split() if len(t) > 2]
    if gt and all(t in a for t in gt):
        return "correct"
    if gt and any(t in a for t in gt):
        return "partial"
    return "wrong"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--t", required=True, help="anchor as MM:SS or seconds (video time)")
    ap.add_argument("--gold", default="", help="founder's gold answer")
    ap.add_argument("--model", default="12b", choices=list(MODELS))
    ap.add_argument("--mem", default=str(DEFAULT_MEM))
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    anchor = parse_t(args.t)
    t0 = time.time()
    res = ask_home.ask(args.question, args.mem, model=MODELS[args.model],
                       timeout=args.timeout, anchor=anchor)
    dt = time.time() - t0

    answer = (res.get("answer") or "").strip()
    refused = bool(res.get("refused"))
    verdict = judge(answer, args.gold, refused)

    print(f"\n  Q (@{args.t} / {anchor:.0f}s, {args.model}): {args.question}")
    print(f"  BRAIN : {answer}")
    print(f"  source: {res.get('source')}  refused: {refused}  support: {res.get('support')}  ({dt:.1f}s)")
    if args.gold:
        print(f"  GOLD  : {args.gold}")
    print(f"  -> heuristic verdict: {verdict.upper()}  (founder confirms)\n")

    rec = {"t": anchor, "tstr": args.t, "model": args.model, "question": args.question,
           "gold": args.gold, "brain": answer, "source": res.get("source"),
           "refused": refused, "support": res.get("support"), "verdict": verdict,
           "secs": round(dt, 1)}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
