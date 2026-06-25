#!/usr/bin/env python3
"""Resumable, live RAS evaluation — so the scoreboard never stalls.

The assembler answers a reasoning question in ~tens of seconds; 25 of them plus a
judge per item runs long enough that a session/usage-limit kill used to lose the
WHOLE run (run_ras writes only at the end). This runner instead checkpoints EVERY
answered+judged question to a JSONL immediately and updates a live status file, so:
  * a kill loses at most the in-flight question; re-running resumes where it stopped;
  * the current number (correct/wrong/miss, hard RAS) is always readable on disk —
    the progress bar actually moves.

Objective judging reuses the frozen gold key + auto_score's gemma judge. Unanswerable
items score 'correct' only on an honest refusal; founder_pending items are recorded
but excluded from the hard number.

Usage:
  evaluation/run_live.py --questions <battery.txt> --gold <gold.json>
      --memory <world_memory.json> [--model M] [--checkpoint /tmp/walk_live.jsonl]
      [--status ops/cockpit/eval_live.json]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evaluation"))

import ask_home  # noqa: E402
import auto_score as A  # noqa: E402
from run_ras import _load_questions  # noqa: E402
from trace_memory.adapters.legacy_ask_home import LegacyAskHome  # noqa: E402
from trace_memory.application import Recall  # noqa: E402
from trace_memory.domain import Query  # noqa: E402


@contextlib.contextmanager
def _deadline(seconds: float | None):
    if not seconds or seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handle_timeout(signum, frame):  # pragma: no cover - trivial signal shim
        raise TimeoutError(f"answer timed out after {seconds:.0f}s")

    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _query_with_timeout(recall: Recall, query: Query, memory: str, timeout_s: float) -> Any:
    with _deadline(timeout_s):
        return recall.execute(query, memory)


def _tally(rows):
    c = sum(1 for r in rows if r.get("verdict") == "correct")
    w = sum(1 for r in rows if r.get("verdict") == "wrong")
    m = sum(1 for r in rows if r.get("verdict") == "miss")
    errors = sum(1 for r in rows if r.get("verdict") == "error")
    reviews = sum(1 for r in rows if r.get("verdict") == "needs_review")
    hard = [r for r in rows if not r.get("pending")
            and r.get("verdict") in A.FINAL_VERDICTS]
    hc = sum(1 for r in hard if r["verdict"] == "correct")
    hw = sum(1 for r in hard if r["verdict"] == "wrong")
    nhard = len(hard) or 1
    answered = hc + hw
    return {
        "correct": c, "wrong": w, "miss": m, "error": errors,
        "needs_review": reviews,
        "hard_ras": round((hc - hw) / nhard * 100, 1),
        "halluc_pct": round(hw / answered * 100, 1) if answered else 0.0,
    }


def _write_status(status_path, total, rows, current, clip, current_question=None,
                  state=None, answer_model=None, judge_model=None, message=None):
    t = _tally(rows)
    done = sum(r.get("verdict") in A.FINAL_VERDICTS for r in rows)
    # ETA from the actual per-question latencies seen so far (brain think + grounding
    # gate + LLM judge — each ~30-80s, which is why N questions take minutes, not the
    # instant a string-match would). This is what the cockpit shows as 'time left'.
    lats = [r.get("latency_s", 0) for r in rows if r.get("latency_s")]
    avg = (sum(lats) / len(lats)) if lats else 0.0
    remaining = max(0, total - done)
    eta_s = int(avg * remaining)
    resolved_state = state or ("complete" if current is None and done >= total else "running")
    status_path.write_text(json.dumps({
        "clip": clip, "state": resolved_state,
        "done": done, "total": total, "current_q": current,
        "current_question": current_question,
        **t, "updated_epoch": int(time.time()),
        "answer_model": answer_model, "judge_model": judge_model,
        "models_independent": bool(answer_model and judge_model and answer_model != judge_model),
        "message": message,
        "avg_s_per_q": round(avg, 1), "eta_s": eta_s,
        "eta_human": ("%dm%02ds" % (eta_s // 60, eta_s % 60)) if eta_s else "finishing",
    }, indent=2))
    # Honest cockpit heartbeat: each scored question proves the Chief is alive. A hung
    # question lets the beat go overdue (expected_next_s ~ 3x the avg latency) so the
    # cockpit shows "Chief STOPPED" instead of a frozen-but-green bar. Best-effort.
    try:
        from cockpit_beat import beat as _beat
        if resolved_state == "complete":
            _beat("scoring complete — %d/%d" % (done, total), 900, by="run_live", idle=True)
        elif current is None:
            _beat("scored %s %d/%d — starting next question" % (clip, done, total),
                  max(180, int(avg * 3)), by="run_live")
        else:
            _beat("scoring %s Q%d/%d" % (clip, current, total),
                  max(180, int(avg * 3)), by="run_live")
    except Exception:
        pass


def _append_row(checkpoint, row):
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("a") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="evaluation/ras/walk_outside_20260614.txt")
    ap.add_argument("--gold", default="evaluation/ras/walk_outside_20260614.gold.json")
    ap.add_argument("--memory", default="data/walks/walk_outside_20260614/memory/world_memory.json")
    ap.add_argument("--model", default="gemma3:12b-it-qat",
                    help="legacy alias for --answer-model")
    ap.add_argument("--answer-model", default=None)
    ap.add_argument("--judge-model", default=None,
                    help="independent grading model (defaults to answer model for legacy direct runs)")
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--status", default=None)
    ap.add_argument("--answer-timeout", type=float, default=120.0)
    args = ap.parse_args()
    answer_model = args.answer_model or args.model
    judge_model = args.judge_model or answer_model
    recall = Recall(LegacyAskHome(ask_home, model=answer_model))

    questions = _load_questions(Path(args.questions))
    gold = json.loads(Path(args.gold).read_text())["items"]
    total = len(questions)
    clip = "cold" if "day_in_life" in args.gold else ("walk" if "walk" in args.gold else "other")
    ckpt = Path(args.checkpoint or ("/tmp/trace_%s_live.jsonl" % clip))
    status_path = Path(args.status or ("ops/cockpit/eval_live_%s.json" % clip))

    # Resume: load already-scored question indices.
    latest = {}
    done = set()
    if ckpt.exists():
        for line in ckpt.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                latest[int(r["i"])] = r
            except Exception:
                pass
        done = {i for i, row in latest.items() if row.get("verdict") in A.FINAL_VERDICTS}
        if args.judge_model:
            mixed = [i for i, row in latest.items() if row.get("verdict") in A.FINAL_VERDICTS
                     and (row.get("answer_model") != answer_model
                          or row.get("judge_model") != judge_model)]
            if mixed:
                print("checkpoint rows lack matching answer/judge provenance; "
                      "start a fresh checkpoint instead of mixing evaluator models: "
                      + ", ".join(map(str, mixed)), file=sys.stderr)
                return 2
        print(f"resuming: {len(done)}/{total} already scored")
    rows = [latest[i] for i in sorted(done)]

    for i, q in enumerate(questions, 1):
        if i in done:
            continue
        _write_status(status_path, total, rows, i, clip, q["question"],
                      answer_model=answer_model, judge_model=judge_model,
                      message="answering locally, then grading independently")
        g = gold.get(str(i), {})
        prior = latest.get(i, {})
        if prior.get("verdict") in A.UNRESOLVED_VERDICTS and isinstance(prior.get("answer"), str):
            answer = prior["answer"]
            dt = float(prior.get("latency_s") or 0)
            print(f"[{i}/{total}] reusing answer while retrying unresolved grade")
        else:
            t0 = time.time()
            try:
                answer = _query_with_timeout(
                    recall, Query(q["question"]), args.memory, args.answer_timeout
                ).text
            except TimeoutError as exc:
                dt = time.time() - t0
                row = {
                    "i": i, "question": q["question"], "answer": "",
                    "verdict": "miss", "pending": False, "latency_s": round(dt, 1),
                    "answer_model": answer_model, "judge_model": judge_model,
                    "grading": {"method": "answer_timeout", "error": str(exc)},
                    "needs_review": False,
                }
                _append_row(ckpt, row)
                rows.append(row)
                _write_status(status_path, total, rows, None, clip,
                              answer_model=answer_model, judge_model=judge_model,
                              message=f"Q{i} timed out and was counted as miss")
                print(f"[Q{i}] timeout: {exc}", file=sys.stderr)
                continue
            except Exception as exc:
                dt = time.time() - t0
                row = {
                    "i": i, "question": q["question"], "answer": "",
                    "verdict": "error", "pending": False, "latency_s": round(dt, 1),
                    "answer_model": answer_model, "judge_model": judge_model,
                    "grading": {"method": "answer_runtime_error", "error": str(exc)},
                    "needs_review": True,
                }
                _append_row(ckpt, row)
                rows.append(row)
                _write_status(status_path, total, rows, None, clip, state="error",
                              answer_model=answer_model, judge_model=judge_model,
                              message=f"answer model failed at Q{i}; explicit error checkpointed")
                print(f"[Q{i}] answer error: {exc}", file=sys.stderr)
                return 2
            dt = time.time() - t0

        pending = bool(g.get("founder_pending"))
        if g.get("unanswerable"):
            verdict = "correct" if A._is_refusal(answer) else "wrong"
            grading = {"method": "structural_unanswerable"}
        elif pending:
            verdict = A._best_guess_pending(answer, g.get("accept", []), g.get("reject", []))
            grading = {"method": "structural_pending_best_guess"}
        else:
            decision = A.grade_answer(
                q["question"], g.get("gold", ""), g.get("accept", []),
                g.get("reject", []), answer, judge_model,
            )
            verdict = decision.verdict
            grading = decision.metadata()

        row = {"i": i, "question": q["question"], "answer": answer,
               "verdict": verdict, "pending": pending, "latency_s": round(dt, 1),
               "answer_model": answer_model, "judge_model": judge_model,
               "models_independent": answer_model != judge_model, "grading": grading,
               "needs_review": verdict in A.UNRESOLVED_VERDICTS}
        rows.append(row)
        _append_row(ckpt, row)
        if verdict in A.UNRESOLVED_VERDICTS:
            unresolved_state = "error" if verdict == "error" else "needs_review"
            _write_status(status_path, total, rows, None, clip, state=unresolved_state,
                          answer_model=answer_model, judge_model=judge_model,
                          message=f"Q{i} grading is {unresolved_state}; score not finalized")
            print(f"[Q{i}] grading {unresolved_state}: {grading}", file=sys.stderr)
            if verdict == "error":
                return 2
            # needs_review: HOLD this item out for human adjudication but keep scoring the
            # rest. One ambiguous judge verdict must never abort the whole baseline — it is
            # already excluded from hard_ras/halluc (only FINAL_VERDICTS count toward the
            # number), so the score stays honest; the held items are surfaced for review.
            continue
        _write_status(status_path, total, rows, None, clip,
                      answer_model=answer_model, judge_model=judge_model,
                      message="latest question scored")
        t = _tally(rows)
        print(f"[{len(rows)}/{total}] ({dt:4.0f}s) {verdict:7s} | hard_ras={t['hard_ras']:+.0f} "
              f"halluc={t['halluc_pct']:.0f}% | {q['question'][:46]}")

    t = _tally(rows)
    print(f"\nDONE {len(rows)}/{total}  hard_ras={t['hard_ras']:+.1f}  "
          f"correct={t['correct']} wrong={t['wrong']} miss={t['miss']}  halluc={t['halluc_pct']:.1f}%")
    print(json.dumps(t))

    # Append this completed run to the cockpit trajectory — mechanical and honest (every
    # run, dips included). Drives the cockpit's progress sparkline.
    try:
        g = args.gold
        hist = ROOT / "ops" / "cockpit" / "progress_history.jsonl"
        with hist.open("a") as f:
            f.write(json.dumps({"epoch": int(time.time()), "clip": clip,
                                "ras": t["hard_ras"], "halluc_pct": t["halluc_pct"],
                                "correct": t["correct"], "wrong": t["wrong"],
                                "miss": t["miss"], "total": len(rows)}) + "\n")
    except Exception:
        pass
    return 3 if t["needs_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
