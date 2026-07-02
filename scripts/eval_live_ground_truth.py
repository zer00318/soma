#!/usr/bin/env python3
"""Evaluate the brain's live-capture answers against human ground truth.

    .venv/bin/python scripts/eval_live_ground_truth.py [--moment live]
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def ask_brain(moment: str, question: str) -> dict:
    body = json.dumps({"moment_id": moment, "question": question}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8765/ask",
        data=body,
        headers={"content-type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=120))


def judge(question: str, truth: str, brain_answer: str, refused: bool) -> str:
    truth_lower = truth.lower().strip()
    ans_lower = brain_answer.lower().strip()
    is_negative = truth_lower.startswith("there is no") or truth_lower == "no"
    if is_negative:
        if refused:
            return "CORRECT"
        no_markers = ["no ", "not ", "don't have", "didn't see", "isn't", "aren't"]
        if any(m in ans_lower for m in no_markers):
            return "CORRECT"
        return "HALLUCINATION"
    if refused:
        return "FALSE_REFUSAL"
    import re
    # For positive existence questions, any affirmative non-refusal is correct
    if truth_lower == "yes" and not refused:
        refusal_markers = ["don't have", "didn't see", "not confident", "no mention"]
        if not any(m in ans_lower for m in refusal_markers):
            return "CORRECT"
    is_numeric = False
    num_words = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
                 "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}
    try:
        num = int(truth_lower)
        is_numeric = True
        ans_no_ts = re.sub(r"\[\d+\.?\d*s?\]", "", ans_lower)
        ans_no_ts = re.sub(r"\d+\.\d+s?", "", ans_no_ts)
        if re.search(rf"\b{num}\b", ans_no_ts):
            return "CORRECT"
        word = num_words.get(truth_lower)
        if word and re.search(rf"\b{word}\b", ans_no_ts):
            return "CORRECT"
    except ValueError:
        pass
    if not is_numeric and truth_lower in ans_lower:
        return "CORRECT"
    return "WRONG"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moment", default="live")
    ap.add_argument("--gt", default="data/phone_captures/live/ground_truth.json")
    args = ap.parse_args()

    gt = json.loads(Path(args.gt).read_text())
    results = []
    correct = wrong = halluc = false_ref = 0

    for item in gt:
        q = item["question"]
        truth = item["answer"]
        resp = ask_brain(args.moment, q)
        ans = resp["answer"]
        ref = resp.get("refused", False)
        verdict = judge(q, truth, ans, ref)

        if verdict == "CORRECT":
            correct += 1
        elif verdict == "HALLUCINATION":
            halluc += 1
        elif verdict == "FALSE_REFUSAL":
            false_ref += 1
        else:
            wrong += 1

        results.append({
            "question": q,
            "truth": truth,
            "brain": ans[:200],
            "refused": ref,
            "verdict": verdict,
        })
        mark = {"CORRECT": "+", "WRONG": "~", "HALLUCINATION": "!", "FALSE_REFUSAL": "-"}
        print(f"  [{mark[verdict]}] {q}")
        print(f"      truth: {truth}")
        print(f"      brain: {ans[:120]}")
        print()

    total = len(gt)
    print("=" * 60)
    print(f"TOTAL: {total}  CORRECT: {correct}  WRONG: {wrong}  HALLUC: {halluc}  FALSE_REF: {false_ref}")
    print(f"Accuracy: {correct}/{total} = {100*correct/total:.1f}%")
    print(f"Hallucination rate: {halluc}/{total} = {100*halluc/total:.1f}%")
    print(f"False refusal rate: {false_ref}/{total} = {100*false_ref/total:.1f}%")

    out_path = Path(args.gt).with_name("eval_results.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults saved to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
