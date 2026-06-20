#!/usr/bin/env python3
"""Independent, provenance-checked objective critic for TRACE.

The critic reads raw scoring artifacts and asks a separate local 27B model for a
skeptical verdict. WALK and COLD are deliberately separate profiles: their score
checkpoints, answer keys, question batteries, and cockpit outputs cannot be mixed.

Examples:
  python3 scripts/objective_critic.py --clip walk --scoreboard /tmp/walk.jsonl
  python3 scripts/objective_critic.py --clip cold --scoreboard /tmp/cold.jsonl
  python3 scripts/objective_critic.py --clip both \
    --walk-scoreboard /tmp/walk.jsonl --cold-scoreboard /tmp/cold.jsonl

Use ``--validate-only`` to perform every identity/freshness check without calling
Ollama or changing a cockpit result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "ops" / "cockpit"
OLLAMA = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = os.environ.get("CRITIC_MODEL", "gemma3:27b-it-qat")
VALID_VERDICTS = {"correct", "wrong", "miss"}
QUESTION_CATEGORIES = {"objects", "people", "places", "text", "events", "fusion", "other"}


class InputError(ValueError):
    """A scoring artifact is unsafe to criticize."""


@dataclass(frozen=True)
class ClipProfile:
    name: str
    questions: Path
    gold: Path
    out: Path
    description: str


PROFILES = {
    "walk": ClipProfile(
        name="walk",
        questions=ROOT / "evaluation/ras/walk_outside_20260614.txt",
        gold=ROOT / "evaluation/ras/walk_outside_20260614.gold.json",
        out=CK / "critic.json",
        description="the recorded 92-second outdoor WALK with 25 hard questions",
    ),
    "cold": ClipProfile(
        name="cold",
        questions=ROOT / "evaluation/ras/day_in_life_20260618.txt",
        gold=ROOT / "evaluation/ras/day_in_life_20260618.gold.json",
        out=CK / "critic_dil.json",
        description=("the never-tuned-on COLD day-in-life clip with 19 hard questions; "
                     "this is the anti-overfit/generalization test"),
    ),
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_stable(path: Path) -> tuple[bytes, os.stat_result]:
    """Read one immutable snapshot, rejecting a file changed during the read."""
    try:
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc}") from exc
    signature = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    if signature(before) != signature(after):
        raise InputError(f"file changed while being read: {path}")
    if not data:
        raise InputError(f"file is empty: {path}")
    return data, after


def _load_questions(data: bytes, path: Path) -> list[str]:
    questions = []
    for raw in data.decode("utf-8", "replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, separator, tail = line.partition(":")
        if separator and head.strip().lower() in QUESTION_CATEGORIES:
            line = tail.strip()
        questions.append(line)
    if not questions:
        raise InputError(f"no questions found in {path}")
    return questions


def _load_gold(data: bytes, path: Path, total: int) -> dict[str, dict[str, Any]]:
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid gold JSON {path}: {exc}") from exc
    gold = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(gold, dict):
        raise InputError(f"gold file has no object-valued 'items': {path}")
    expected = {str(i) for i in range(1, total + 1)}
    if set(gold) != expected:
        missing = sorted(expected - set(gold), key=int)
        extra = sorted(set(gold) - expected)
        raise InputError(f"gold indices do not match battery (missing={missing}, extra={extra})")
    return gold


def _load_scoreboard(data: bytes, path: Path, questions: list[str]) -> list[dict[str, Any]]:
    rows = []
    for line_no, raw in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(f"malformed scoreboard JSON at {path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise InputError(f"scoreboard row {line_no} is not an object")
        rows.append(row)

    total = len(questions)
    if len(rows) != total:
        raise InputError(f"incomplete scoreboard for this clip: expected {total} rows, got {len(rows)}")
    seen = set()
    for line_no, row in enumerate(rows, 1):
        index = row.get("i")
        if type(index) is not int or not 1 <= index <= total:
            raise InputError(f"invalid question index at scoreboard row {line_no}: {index!r}")
        if index in seen:
            raise InputError(f"duplicate question index in scoreboard: {index}")
        seen.add(index)
        verdict = row.get("verdict")
        if verdict not in VALID_VERDICTS:
            raise InputError(f"invalid verdict for Q{index}: {verdict!r}")
        if not isinstance(row.get("answer"), str):
            raise InputError(f"Q{index} has no string answer")
        actual_q = row.get("question")
        expected_q = questions[index - 1]
        if actual_q != expected_q:
            raise InputError(
                f"question identity mismatch for Q{index}; checkpoint may belong to another clip\n"
                f"  expected: {expected_q!r}\n  found:    {actual_q!r}"
            )
    if seen != set(range(1, total + 1)):
        raise InputError("scoreboard does not contain every question index exactly once")
    return sorted(rows, key=lambda row: row["i"])


def _source_record(path: Path, data: bytes, stat: os.stat_result) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(data),
        "bytes": len(data),
        "mtime_epoch": round(stat.st_mtime, 3),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _validate_freshness(score_stat: os.stat_result, references: list[tuple[Path, os.stat_result]],
                        max_age_hours: float, now: float) -> dict[str, Any]:
    age_seconds = now - score_stat.st_mtime
    if age_seconds < -300:
        raise InputError("scoreboard timestamp is more than five minutes in the future")
    if age_seconds > max_age_hours * 3600:
        raise InputError(
            f"stale scoreboard: age is {age_seconds / 3600:.1f}h, limit is {max_age_hours:.1f}h"
        )
    newer = [(path, stat.st_mtime) for path, stat in references
             if stat.st_mtime > score_stat.st_mtime + 1e-6]
    if newer:
        details = ", ".join(f"{path} ({mtime:.3f})" for path, mtime in newer)
        raise InputError(f"scoreboard predates scoring inputs; rescore required: {details}")
    return {
        "checked_at_epoch": round(now, 3),
        "age_seconds_at_check": round(max(age_seconds, 0), 3),
        "max_age_hours": max_age_hours,
        "newer_than_gold_and_questions": True,
    }


def _history(clip: str) -> list[dict[str, Any]]:
    """Read only mechanically recorded history for this clip, never roadmap prose."""
    path = CK / "progress_history.jsonl"
    if not path.exists():
        return []
    result = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("clip") == clip:
            result.append({key: row.get(key) for key in
                           ("epoch", "ras", "halluc_pct", "correct", "wrong", "miss", "total")})
    return result[-8:]


def prepare_run(profile: ClipProfile, scoreboard: Path, max_age_hours: float,
                now: float | None = None) -> dict[str, Any]:
    """Strictly validate one clip and build evidence from one stable snapshot."""
    question_data, question_stat = _read_stable(profile.questions)
    gold_data, gold_stat = _read_stable(profile.gold)
    score_data, score_stat = _read_stable(scoreboard)
    questions = _load_questions(question_data, profile.questions)
    gold = _load_gold(gold_data, profile.gold, len(questions))
    rows = _load_scoreboard(score_data, scoreboard, questions)
    checked_at = time.time() if now is None else now
    freshness = _validate_freshness(
        score_stat,
        [(profile.questions, question_stat), (profile.gold, gold_stat)],
        max_age_hours,
        checked_at,
    )

    hard = [row for row in rows if not row.get("pending")]
    correct = sum(row["verdict"] == "correct" for row in hard)
    wrong = sum(row["verdict"] == "wrong" for row in hard)
    miss = sum(row["verdict"] == "miss" for row in hard)
    answered = correct + wrong
    denominator = len(hard)
    current = {
        "correct": correct,
        "wrong": wrong,
        "miss": miss,
        "ras": round((correct - wrong) / denominator * 100, 1),
        "halluc_pct": round(wrong / answered * 100, 1) if answered else 0.0,
        "n_scored": denominator,
        "n_pending_excluded": len(rows) - denominator,
    }
    qlines = []
    for row in hard:
        item = gold[str(row["i"])]
        accept = item.get("accept", [])
        qlines.append(
            "Q%s [%s] acceptN=%d | Q:%s | GOLD:%s | ENGINE:%s" % (
                row["i"], row["verdict"], len(accept), questions[row["i"] - 1][:90],
                str(item.get("gold", ""))[:140].replace("\n", " "),
                row["answer"][:180].replace("\n", " "),
            )
        )
    try:
        gitlog = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--oneline", "-15"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
    except Exception:
        gitlog = ""

    provenance = {
        "schema": 1,
        "clip": profile.name,
        "scoreboard": _source_record(scoreboard, score_data, score_stat),
        "gold": _source_record(profile.gold, gold_data, gold_stat),
        "questions": _source_record(profile.questions, question_data, question_stat),
        "freshness": freshness,
    }
    evidence = {
        "clip": profile.name,
        "clip_description": profile.description,
        "metric_definition": (
            f"RAS = (correct - made_up) / {denominator} * 100 for non-pending questions. "
            "A confident wrong answer is made_up. A refusal is a miss: it does not add a "
            "penalty beyond failing to earn a correct, so refusal rate must be inspected."
        ),
        "current": current,
        "per_question": qlines,
        "score_trajectory_for_this_clip_only": _history(profile.name),
        "recent_commits": gitlog,
        "n_gold_with_broad_accept": sum(
            len(item.get("accept", [])) >= 6 for item in gold.values()
        ),
        "input_provenance": provenance,
    }
    return {"profile": profile, "scoreboard": scoreboard, "evidence": evidence,
            "provenance": provenance}


CHARTER = """You are an INDEPENDENT, SKEPTICAL auditor of a solo founder's AI project, TRACE.
You did not build it. Your loyalty is to the founder and the truth. Be specific, fair, and
grounded ONLY in the evidence below. Never infer progress from claims that are not measured.

TRACE turns a day into text without retaining video/audio, then answers questions truthfully,
citing what was perceived and refusing when evidence is inadequate. This evidence is for
__CLIP_DESC__. Treat the input provenance as part of the audit.

Judge skeptically:
1. Is the number honest and meaningful, considering correct, refused, and made-up answers?
2. Is this clip measurably progressing, or is it churning? Say "unproven" if its filtered
   trajectory has too little comparable history.
3. Do the results expose overfitting or failure to generalize? Do not treat one clip as proof
   about the other clip; WALK and COLD receive separate verdicts.
4. What uncomfortable truth is the engineer probably missing?

Reply with ONLY a JSON object, exactly this shape:
{
 "doing_it_right": "yes|mostly|mixed|no",
 "headline": "one honest sentence",
 "whats_real": ["genuine, verifiable progress ..."],
 "whats_suspect": ["inflated/gamed/overfit/unverified ..."],
 "biggest_risks": ["..."],
 "course_corrections": ["concrete, prioritized ..."],
 "plain_english_for_founder": "4-8 sentences, no jargon"
}

EVIDENCE (raw scoring artifacts, not the engineer's summary):
__EVIDENCE__
"""


def _gen(prompt: str, model: str, timeout: int) -> str:
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    }).encode()
    request = urllib.request.Request(
        OLLAMA, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace")).get("response", "").strip()


def _parse_verdict(text: str) -> dict[str, Any] | None:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        verdict = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    required_lists = ("whats_real", "whats_suspect", "biggest_risks", "course_corrections")
    if not isinstance(verdict, dict) or verdict.get("doing_it_right") not in {
            "yes", "mostly", "mixed", "no"}:
        return None
    if not all(isinstance(verdict.get(key), list) for key in required_lists):
        return None
    if not all(isinstance(verdict.get(key), str) for key in
               ("headline", "plain_english_for_founder")):
        return None
    return verdict


def _atomic_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _run_one(prepared: dict[str, Any], model: str, timeout: int) -> bool:
    profile: ClipProfile = prepared["profile"]
    evidence = prepared["evidence"]
    provenance = prepared["provenance"]
    started = datetime.now(timezone.utc).isoformat()
    base = {
        "state": "running",
        "clip": profile.name,
        "model_id": model,
        "started_utc": started,
        "input_provenance": provenance,
    }
    # Clear any old verdict before the model call. A failed fresh attempt must never
    # leave an earlier success looking current.
    _atomic_json(profile.out, base)
    current = evidence["current"]
    print(f"[critic:{profile.name}] {model} judging {current['n_scored']} questions "
          f"(RAS {current['ras']:.1f}, {current['wrong']} made-up)...", flush=True)
    prompt = CHARTER.replace("__CLIP_DESC__", profile.description).replace(
        "__EVIDENCE__", json.dumps(evidence, ensure_ascii=False, indent=1)
    )
    try:
        raw = _gen(prompt, model, timeout)
        verdict = _parse_verdict(raw)
        if not verdict:
            raise RuntimeError(f"model returned invalid verdict JSON: {raw[:300]}")
    except Exception as exc:
        failed = {**base, "state": "failed", "failed_utc": datetime.now(timezone.utc).isoformat(),
                  "error": str(exc)}
        _atomic_json(profile.out, failed)
        print(f"[critic:{profile.name}] failed: {exc}", file=sys.stderr)
        return False

    completed = datetime.now(timezone.utc).isoformat()
    output = {
        **base,
        "state": "complete",
        "completed_utc": completed,
        "verdict": verdict,
        "evidence_snapshot": current,
        "model": f"Independent local critic: {model} · judged {current['n_scored']} questions",
        "generated": (f"Independent {profile.name.upper()} critic completed {completed} "
                      f"with local {model}; inputs are hash-pinned below"),
    }
    _atomic_json(profile.out, output)
    print(f"[critic:{profile.name}] wrote {profile.out} — "
          f"doing_it_right: {verdict['doing_it_right']}")
    return True


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", choices=("walk", "cold", "both"), required=True)
    parser.add_argument("--scoreboard", type=Path,
                        help="checkpoint for a single --clip walk/cold run")
    parser.add_argument("--walk-scoreboard", type=Path,
                        help="WALK checkpoint (required with --clip both)")
    parser.add_argument("--cold-scoreboard", type=Path,
                        help="COLD checkpoint (required with --clip both)")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    if args.clip == "both":
        if args.scoreboard or not args.walk_scoreboard or not args.cold_scoreboard:
            parser.error("--clip both requires --walk-scoreboard and --cold-scoreboard only")
    elif not args.scoreboard or args.walk_scoreboard or args.cold_scoreboard:
        parser.error("a single --clip walk/cold run requires --scoreboard only")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    pairs = (
        [(PROFILES["walk"], args.walk_scoreboard), (PROFILES["cold"], args.cold_scoreboard)]
        if args.clip == "both" else [(PROFILES[args.clip], args.scoreboard)]
    )
    try:
        # Preflight everything before either 27B call. A bad COLD checkpoint cannot
        # produce a misleading half-complete "both" run after WALK has already run.
        prepared = [prepare_run(profile, scoreboard.resolve(), args.max_age_hours)
                    for profile, scoreboard in pairs]
    except InputError as exc:
        print(f"[critic] input rejected: {exc}", file=sys.stderr)
        return 2

    for item in prepared:
        ev = item["evidence"]
        source = item["provenance"]["scoreboard"]
        print(f"[critic:{ev['clip']}] validated {ev['current']['n_scored']} rows; "
              f"age={item['provenance']['freshness']['age_seconds_at_check']:.0f}s; "
              f"sha256={source['sha256'][:12]}…; source={source['path']}")
    if args.validate_only:
        return 0
    # In a two-clip run, clear both old verdicts before the first slow model call.
    # Otherwise COLD could still look current for minutes while WALK is running.
    queued_at = datetime.now(timezone.utc).isoformat()
    for item in prepared:
        profile = item["profile"]
        _atomic_json(profile.out, {
            "state": "queued",
            "clip": profile.name,
            "model_id": args.model,
            "queued_utc": queued_at,
            "input_provenance": item["provenance"],
        })
    successes = [_run_one(item, args.model, args.timeout) for item in prepared]
    return 0 if all(successes) else 1


if __name__ == "__main__":
    sys.exit(main())
