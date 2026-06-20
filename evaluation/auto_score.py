#!/usr/bin/env python3
"""Objective auto-scorer for the RAS battery.

Stops the lead hand-judging every loop. Reads a frozen gold answer key and a
run_ras `answers.json`, and emits a verdict per item plus the headline numbers.

Drafted via local qwen2.5-coder:14b, then hardened with structural fast paths,
a strict independent local judge contract, and explicit unresolved states.

Verdict logic (gold keyed 1-based, matching battery order):
  - unanswerable==true : 'correct' iff the engine HONESTLY refuses (a guess is
                         'wrong' — refusing to answer the unanswerable is the
                         whole point of a memory product that doesn't confabulate).
  - founder_pending==true : 'pending'. Recorded, but EXCLUDED from the hard
                         number until the founder confirms ground truth.
  - else : deterministic rubric checks run first; semantic cases go to a separately
           configurable local judge. Runtime/parse failures are ERROR, never MISS.

Numbers:
  hard_ras       = (correct - wrong) / n_hard * 100      over non-pending items
  hallucination  = wrong / (correct + wrong) * 100       of the answered, how many lied
  full_ras       = same RAS over ALL items, scoring each pending item by gold
                   best-guess (accept-cue present -> correct, honest refusal ->
                   miss, else -> wrong) so the founder can see the optimistic ceiling.

Usage:
  evaluation/auto_score.py --gold <gold.json> --answers <answers.json> [--model M] [--json-only]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
JUDGE_MODEL = "gemma3:27b-it-qat"

# Phrases that signal an HONEST "I don't have / didn't capture that" answer.
# Used both for unanswerable items (refusal == correct) and as a deterministic
# fast-path so the judge is never asked to grade an obvious refusal.
_REFUSAL_CUES = (
    "don't track", "dont track", "do not track",
    "don't have", "dont have", "do not have", "not in my memory",
    "no data", "no record", "not recorded", "didn't record", "didn't capture",
    "i don't know", "i dont know", "don't know",
    "not sure", "can't tell", "cannot tell", "can't say", "cannot say",
    "unanswerable", "didn't see", "did not see", "didn't read enough",
    "no idea", "unable to", "not able to", "i don't recall", "don't recall",
    "can't confirm", "cannot confirm", "couldn't confirm", "could not confirm",
    "can't determine", "cannot determine", "couldn't determine", "could not determine",
    "wasn't detected whether", "was not detected whether", "not detected whether",
)

FINAL_VERDICTS = {"correct", "wrong", "miss"}
UNRESOLVED_VERDICTS = {"error", "needs_review"}


@dataclass(frozen=True)
class GradeDecision:
    verdict: str
    method: str
    judge_model: Optional[str] = None
    judge_raw: Optional[str] = None
    error: Optional[str] = None
    review_reason: Optional[str] = None

    def metadata(self) -> dict:
        return {key: value for key, value in {
            "method": self.method,
            "judge_model": self.judge_model,
            "judge_raw": self.judge_raw,
            "error": self.error,
            "review_reason": self.review_reason,
        }.items() if value is not None}


def _is_refusal(answer: str) -> bool:
    a = (answer or "").strip().lower()
    if not a:
        return True
    return any(cue in a for cue in _REFUSAL_CUES)


def _cue_present(answer: str, cue: object) -> bool:
    """Literal cue match with boundaries and answer-citation timestamps removed."""
    text = (answer or "").lower().replace("’", "'")
    text = re.sub(r"\b(?:read\s+at\s+)?t\s*=\s*\d+(?:\.\d+)?s?\b", " ", text)
    needle = str(cue or "").strip().lower().replace("’", "'")
    if not needle:
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", text))


def _matching_cues(answer: str, cues: list) -> list[str]:
    return [str(cue) for cue in (cues or []) if _cue_present(answer, cue)]


def _asserts_cue(answer: str, cues: list) -> bool:
    return bool(_matching_cues(answer, cues))


_EPISTEMIC_GOLD_RE = re.compile(
    r"\b(could not confirm|couldn't confirm|cannot confirm|can't confirm|"
    r"insufficient context(?: to claim)?|not enough (?:context|evidence)|"
    r"fundamentally unknowable|unanswerable)\b", re.I)


def _explicit_epistemic_gold(gold: str) -> bool:
    """True only when the key says uncertainty itself is the correct fact."""
    return bool(_EPISTEMIC_GOLD_RE.search(gold or ""))


def _long_quotes(text: str) -> list[str]:
    quotes = re.findall(r'["“](.*?)["”]', text or "", flags=re.S)
    return [re.sub(r"\s+", " ", quote).strip().lower() for quote in quotes
            if len(re.sub(r"\s+", " ", quote).strip()) >= 24]


def _clear_quoted_mismatch(gold: str, engine: str) -> bool:
    """Detect a confidently supplied long quote that is plainly a different quote."""
    gold_quotes = _long_quotes(gold)
    engine_quotes = _long_quotes(engine)
    if not gold_quotes or not engine_quotes:
        return False
    best = max(difflib.SequenceMatcher(None, expected, actual).ratio()
               for expected in gold_quotes for actual in engine_quotes)
    return best < 0.50


def deterministic_grade(gold: str, accept: list, reject: list,
                        engine: str) -> Optional[GradeDecision]:
    """Grade only cases whose frozen rubric has an unambiguous structural answer."""
    if _is_refusal(engine):
        if _explicit_epistemic_gold(gold):
            return GradeDecision("correct", "structural_epistemic_gold")
        return GradeDecision("miss", "structural_refusal")

    accepted = _matching_cues(engine, accept)
    rejected = _matching_cues(engine, reject)
    # A specifically rejected assertion dominates a broad accepted token, e.g.
    # "no child" contains "child" but is explicitly wrong for a positive gold.
    if rejected:
        return GradeDecision("wrong", "structural_reject_cue")
    if accepted:
        return GradeDecision("correct", "structural_accept_cue")
    if _clear_quoted_mismatch(gold, engine):
        return GradeDecision("wrong", "structural_quoted_mismatch")
    return None


def _judge_prompt(question: str, gold: str, accept: list, reject: list, engine: str) -> str:
    """A deterministic, closed-form rubric. The judge outputs ONE word only."""
    accept_str = "; ".join(accept) if accept else "(none given)"
    reject_str = "; ".join(reject) if reject else "(none given)"
    return f"""You are a STRICT grader for a perception-memory system. Output EXACTLY one lowercase word: correct, wrong, or miss. No punctuation, no explanation, no other text.

Definitions:
- correct: the ENGINE ANSWER conveys the GOLD answer. At least one ACCEPT cue is present (in meaning, not necessarily verbatim) AND no REJECT cue is asserted.
- wrong: the ENGINE ANSWER confidently states something that matches a REJECT cue, or confidently contradicts the GOLD answer. Confident-but-false = wrong.
- miss: the ENGINE ANSWER is an honest "I don't have / don't know / didn't see / not sure" or is empty. A refusal is NEVER wrong.

Rules:
- Judge meaning, not wording. A correct fact with extra hedging is still correct.
- If the engine asserts a fact present in REJECT cues, that is wrong even if it also mentions something correct.
- If the engine declines to answer (no committed fact), it is miss, never wrong.
- Be conservative: only say correct when an accept cue is genuinely satisfied.

QUESTION: {question}
GOLD ANSWER: {gold}
ACCEPT cues (any one satisfies correctness): {accept_str}
REJECT cues (asserting any -> wrong): {reject_str}
ENGINE ANSWER: {engine}

One word (correct|wrong|miss):"""


def _parse_verdict(raw: str) -> Optional[str]:
    """Accept the promised one-token contract; anything else is a grading error."""
    token = (raw or "").strip().lower()
    return token if token in FINAL_VERDICTS else None


def _request_judge(question: str, gold: str, accept: list, reject: list,
                   engine: str, model: str) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": _judge_prompt(question, gold, accept, reject, engine),
        "stream": False,
        "options": {"temperature": 0, "top_p": 1, "seed": 0},
    }).encode("utf-8")
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return str(body.get("response", ""))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"judge request failed: {exc}") from exc


def grade_answer(question: str, gold: str, accept: list, reject: list,
                 engine: str, judge_model: str) -> GradeDecision:
    """Return a provenance-bearing grade; never turn judge failure into MISS."""
    structural = deterministic_grade(gold, accept, reject, engine)
    if structural is not None:
        return structural
    try:
        raw = _request_judge(question, gold, accept, reject, engine, judge_model)
    except Exception as exc:
        return GradeDecision(
            "error", "judge_runtime_error", judge_model=judge_model, error=str(exc)
        )
    verdict = _parse_verdict(raw)
    if verdict is None:
        return GradeDecision(
            "error", "judge_parse_error", judge_model=judge_model,
            judge_raw=raw[:1000], error="judge did not return exactly correct|wrong|miss",
        )
    # By rubric, MISS is reserved for empty/epistemic refusals. A semantic judge
    # trying to neutralize a committed specific answer requires adjudication.
    if verdict == "miss" and not _is_refusal(engine):
        return GradeDecision(
            "needs_review", "judge_contract_conflict", judge_model=judge_model,
            judge_raw=raw[:1000],
            review_reason="judge returned miss for a non-refusal answer",
        )
    return GradeDecision(verdict, "independent_llm_judge", judge_model=judge_model,
                         judge_raw=raw[:1000])


def _call_judge(question: str, gold: str, accept: list, reject: list,
                engine: str, model: str) -> str:
    """Compatibility wrapper that fails loudly on unresolved grades."""
    decision = grade_answer(question, gold, accept, reject, engine, model)
    if decision.verdict not in FINAL_VERDICTS:
        raise RuntimeError(decision.error or decision.review_reason or decision.verdict)
    return decision.verdict


def _best_guess_pending(answer: str, accept: list, reject: list) -> str:
    """Offline heuristic verdict for a founder_pending item, for full_ras only.

    No gemma call (the gold is itself provisional). Accept cue present and no
    reject cue -> correct; honest refusal -> miss; asserted reject cue -> wrong;
    otherwise -> miss (don't reward an unverified guess as correct)."""
    if _asserts_cue(answer, reject):
        return "wrong"
    # accept BEFORE refusal: an absence-gold answer ("didn't see an iPhone")
    # reads as a refusal yet is the correct fact, so the cue wins.
    if _asserts_cue(answer, accept):
        return "correct"
    if _is_refusal(answer):
        return "miss"
    return "miss"


def score(gold_path: Path, answers_path: Path, model: str) -> dict:
    gold = json.loads(gold_path.read_text())["items"]
    answers = json.loads(answers_path.read_text())["answers"]

    n = len(gold)
    rows = []  # (idx, verdict, pending_bool, pending_guess_or_None, question)
    for i in range(1, n + 1):
        g = gold[str(i)]
        a = answers[i - 1] if i - 1 < len(answers) else {"answer": ""}
        engine = a.get("answer", "") or ""
        q = g.get("q", "")
        accept = g.get("accept", []) or []
        reject = g.get("reject", []) or []

        pending_guess = None
        if g.get("unanswerable"):
            verdict = "correct" if _is_refusal(engine) else "wrong"
            pending = False
        elif g.get("founder_pending"):
            verdict = "pending"
            pending = True
            pending_guess = _best_guess_pending(engine, accept, reject)
        else:
            decision = grade_answer(q, g.get("gold", ""), accept, reject, engine, model)
            verdict = decision.verdict
            pending = False
        rows.append((i, verdict, pending, pending_guess, q))

    correct = sum(1 for _, v, p, _, _ in rows if not p and v == "correct")
    wrong = sum(1 for _, v, p, _, _ in rows if not p and v == "wrong")
    miss = sum(1 for _, v, p, _, _ in rows if not p and v == "miss")
    pending = sum(1 for _, _, p, _, _ in rows if p)
    errors = sum(1 for _, v, p, _, _ in rows if not p and v == "error")
    needs_review = sum(1 for _, v, p, _, _ in rows if not p and v == "needs_review")
    n_hard = n - pending
    answered = correct + wrong

    hard_ras = (correct - wrong) / n_hard * 100 if n_hard else 0.0
    halluc = (wrong / answered * 100) if answered else 0.0

    # full_ras: fold pending items in via their best-guess verdict.
    fc = correct + sum(1 for _, _, p, g, _ in rows if p and g == "correct")
    fw = wrong + sum(1 for _, _, p, g, _ in rows if p and g == "wrong")
    full_ras = (fc - fw) / n * 100 if n else 0.0

    return {
        "rows": rows,
        "summary": {
            "n_total": n,
            "n_hard": n_hard,
            "correct": correct,
            "wrong": wrong,
            "miss": miss,
            "error": errors,
            "needs_review": needs_review,
            "pending": pending,
            "hard_ras": round(hard_ras, 1),
            "full_ras": round(full_ras, 1),
            "hallucination_pct": round(halluc, 1),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Objective RAS auto-scorer (gemma judge).")
    ap.add_argument("--gold", required=True, help="frozen gold answer-key JSON")
    ap.add_argument("--answers", required=True, help="run_ras answers.json")
    ap.add_argument("--model", default=JUDGE_MODEL, help="ollama judge model")
    ap.add_argument("--json-only", action="store_true", help="print only the summary JSON line")
    args = ap.parse_args()

    res = score(Path(args.gold), Path(args.answers), args.model)
    rows, summary = res["rows"], res["summary"]

    if not args.json_only:
        print(f"\nauto-score: {Path(args.answers).name}  vs  {Path(args.gold).name}")
        print(f"{'#':>3}  {'verdict':<8}  question")
        print(f"{'-'*3}  {'-'*8}  {'-'*48}")
        for idx, verdict, pending, guess, q in rows:
            tag = verdict + (f"~{guess}" if pending and guess else "")
            print(f"{idx:>3}  {tag:<8}  {q[:60]}")
        s = summary
        print()
        print(f"  hard items     : {s['n_hard']} ({s['correct']} correct / "
              f"{s['wrong']} wrong / {s['miss']} miss)   pending: {s['pending']}")
        print(f"  hard_ras       = {s['hard_ras']:6.1f}   (pitch gate: >= 60)")
        print(f"  hallucination  = {s['hallucination_pct']:6.1f}%  (pitch gate: < 5%)")
        print(f"  full_ras       = {s['full_ras']:6.1f}   (pending folded in by gold best-guess)")
        if s["error"] or s["needs_review"]:
            print(f"  unresolved     : {s['error']} error / {s['needs_review']} needs review")
        print()

    print(json.dumps(summary, ensure_ascii=False))
    if summary["error"] or summary["needs_review"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
