#!/usr/bin/env python3
"""Run the WALK and COLD RAS batteries sequentially with durable lane state.

This is deliberately a thin orchestrator around ``evaluation/run_live.py``.
That runner owns per-question answering and judging; this script owns the
two-clip contract: independent checkpoints, visible queue state, input identity,
single-process execution, and completion validation.

The default model is served by Ollama on localhost. Non-Gemma model names are
rejected, and no remote model endpoint is accepted.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gemma3:12b-it-qat"
DEFAULT_JUDGE_MODEL = "gemma3:27b-it-qat"
LOCAL_OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
MODEL_RE = re.compile(r"^gemma[-0-9A-Za-z_.:]*$")


@dataclass(frozen=True)
class ClipSpec:
    name: str
    questions: Path
    gold: Path
    memory: Path
    checkpoint: Path
    status: Path


def default_specs(root: Path = ROOT) -> dict[str, ClipSpec]:
    cockpit = root / "ops" / "cockpit"
    checkpoints = cockpit / "rescore_checkpoints"
    return {
        "walk": ClipSpec(
            name="walk",
            questions=root / "evaluation" / "ras" / "walk_outside_20260614.txt",
            gold=root / "evaluation" / "ras" / "walk_outside_20260614.gold.json",
            memory=root / "data" / "walks" / "walk_outside_20260614" / "memory" / "world_memory.json",
            checkpoint=checkpoints / "walk.jsonl",
            status=cockpit / "eval_live_walk.json",
        ),
        "cold": ClipSpec(
            name="cold",
            questions=root / "evaluation" / "ras" / "day_in_life_20260618.txt",
            gold=root / "evaluation" / "ras" / "day_in_life_20260618.gold.json",
            memory=root / "data" / "walks" / "day_in_life_20260618" / "memory" / "world_memory.json",
            checkpoint=checkpoints / "cold.jsonl",
            status=cockpit / "eval_live_cold.json",
        ),
    }


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def _question_count(path: Path) -> int:
    return sum(1 for raw in path.read_text().splitlines()
               if raw.strip() and not raw.strip().startswith("#"))


def _checkpoint_rows(path: Path, total: int) -> dict[int, dict]:
    """Return latest finalized rows; a later ERROR invalidates an earlier grade."""
    latest: dict[int, dict] = {}
    if not path.exists():
        return latest
    for raw in path.read_text().splitlines():
        try:
            row = json.loads(raw)
            index = int(row["i"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if 1 <= index <= total and row.get("verdict") in {
                "correct", "wrong", "miss", "error", "needs_review"}:
            latest[index] = row
    return {index: row for index, row in latest.items()
            if row.get("verdict") in {"correct", "wrong", "miss"}}


def _checkpoint_issues(path: Path, total: int) -> dict[int, dict]:
    latest: dict[int, dict] = {}
    if not path.exists():
        return latest
    for raw in path.read_text().splitlines():
        try:
            row = json.loads(raw)
            index = int(row["i"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if 1 <= index <= total:
            latest[index] = row
    return {index: row for index, row in latest.items()
            if row.get("verdict") in {"error", "needs_review"}}


def _checkpoint_attempted(path: Path, total: int) -> dict[int, dict]:
    """Indices the runner has RESOLVED or explicitly HELD (correct/wrong/miss/
    needs_review). A lane is 'all attempted' when this covers 1..total: there is nothing
    left that could still be scored. needs_review items are held OUT of the score (see
    _checkpoint_rows / _tally) but must not make a finished lane look forever-incomplete —
    one ambiguous judge verdict shouldn't abort the two-clip baseline."""
    latest: dict[int, dict] = {}
    if not path.exists():
        return latest
    for raw in path.read_text().splitlines():
        try:
            row = json.loads(raw)
            index = int(row["i"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if 1 <= index <= total:
            latest[index] = row
    return {index: row for index, row in latest.items()
            if row.get("verdict") in {"correct", "wrong", "miss", "needs_review"}}


def _tally(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    hard = [row for row in rows if not row.get("pending")]
    correct = sum(row.get("verdict") == "correct" for row in rows)
    wrong = sum(row.get("verdict") == "wrong" for row in rows)
    miss = sum(row.get("verdict") == "miss" for row in rows)
    hard_correct = sum(row.get("verdict") == "correct" for row in hard)
    hard_wrong = sum(row.get("verdict") == "wrong" for row in hard)
    answered = hard_correct + hard_wrong
    return {
        "correct": correct,
        "wrong": wrong,
        "miss": miss,
        "hard_ras": round((hard_correct - hard_wrong) / len(hard) * 100, 1) if hard else 0.0,
        "halluc_pct": round(hard_wrong / answered * 100, 1) if answered else 0.0,
    }


def _hash_file(digest: "hashlib._Hash", path: Path, label: str) -> None:
    digest.update(label.encode())
    digest.update(b"\0")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)


def input_fingerprint(spec: ClipSpec, root: Path = ROOT) -> str:
    """Fingerprint score inputs and the brain/judge code that determines answers."""
    digest = hashlib.sha256()
    for label, path in (("questions", spec.questions), ("gold", spec.gold)):
        _hash_file(digest, path, label)

    memory_dir = spec.memory.parent
    for path in sorted(memory_dir.iterdir()):
        if not path.is_file() or ".ckpt." in path.name:
            continue
        if path.suffix.lower() not in {".json", ".jsonl", ".ndjson", ".txt"}:
            continue
        _hash_file(digest, path, "memory/" + path.name)

    code_files = (
        "evaluation/run_live.py", "evaluation/auto_score.py", "scripts/ask_home.py",
        "scripts/artifact_provenance.py", "scripts/audio_events.py",
        "scripts/build_temporal_index.py", "scripts/counting_specialist.py",
        "scripts/entity_graph.py", "scripts/evidence_confidence.py",
        "scripts/screen_reader.py", "scripts/self_entity.py",
        "scripts/semantic_index.py", "scripts/temporal_specialist.py",
    )
    for rel in code_files:
        path = root / rel
        if path.exists():
            _hash_file(digest, path, rel)
    return digest.hexdigest()


def _meta_path(spec: ClipSpec) -> Path:
    return spec.checkpoint.with_suffix(spec.checkpoint.suffix + ".meta.json")


def _archive(path: Path) -> None:
    if not path.exists():
        return
    suffix = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(path.name + ".bak-" + suffix)
    serial = 1
    while target.exists():
        target = path.with_name(path.name + f".bak-{suffix}-{serial}")
        serial += 1
    shutil.move(path, target)


def prepare_checkpoint(spec: ClipSpec, fingerprint: str, model: str,
                       fresh: bool = False, judge_model: str | None = None) -> None:
    judge_model = judge_model or model
    spec.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    meta_path = _meta_path(spec)
    if fresh:
        _archive(spec.checkpoint)
        _archive(meta_path)

    previous = None
    if meta_path.exists():
        try:
            previous = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            previous = None
    if spec.checkpoint.exists() and spec.checkpoint.stat().st_size and (
        not previous
        or previous.get("fingerprint") != fingerprint
        or previous.get("answer_model", previous.get("model")) != model
        or previous.get("judge_model", previous.get("model")) != judge_model
    ):
        raise RuntimeError(
            f"{spec.name} checkpoint belongs to different inputs/model; "
            "restart with --fresh instead of mixing scores"
        )
    _atomic_json(meta_path, {
        "clip": spec.name,
        "fingerprint": fingerprint,
        "model": model,
        "answer_model": model,
        "judge_model": judge_model,
        "models_independent": model != judge_model,
        "questions": str(spec.questions),
        "gold": str(spec.gold),
        "memory": str(spec.memory),
        "updated_epoch": int(time.time()),
    })


def lane_status(spec: ClipSpec, state: str, total: int, rows: dict[int, dict],
                model: str, run_id: str, message: str, judge_model: str | None = None,
                **extra: object) -> dict:
    judge_model = judge_model or model
    eta = {
        "queued": "waiting for earlier clip",
        "running": "calculating from live question timings",
        "complete": "done",
        "failed": "resume available",
        "needs_review": "human adjudication required",
    }.get(state, "unknown")
    payload = {
        "clip": spec.name,
        "state": state,
        "done": len(rows),
        "total": total,
        "current_q": None,
        "current_question": None,
        **_tally(rows.values()),
        "model": model,
        "answer_model": model,
        "judge_model": judge_model,
        "models_independent": model != judge_model,
        "model_runtime": "local ollama",
        "local_only": True,
        "checkpoint": str(spec.checkpoint),
        "resumable": state != "complete",
        "run_id": run_id,
        "message": message,
        "eta_human": eta,
        "updated_epoch": int(time.time()),
        **extra,
    }
    _atomic_json(spec.status, payload)
    return payload


def validate_spec(spec: ClipSpec) -> int:
    for path in (spec.questions, spec.gold, spec.memory):
        if not path.is_file():
            raise FileNotFoundError(f"missing {spec.name} input: {path}")
    total = _question_count(spec.questions)
    gold = json.loads(spec.gold.read_text()).get("items", {})
    missing = [str(i) for i in range(1, total + 1) if str(i) not in gold]
    if missing:
        raise ValueError(f"{spec.name} gold key is missing question(s): {', '.join(missing)}")
    return total


def assert_local_gemma(model: str, timeout: float = 8.0) -> None:
    if not MODEL_RE.fullmatch(model):
        raise ValueError(f"only local Gemma models are allowed, got {model!r}")
    request = urllib.request.Request(LOCAL_OLLAMA_TAGS, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            models = json.loads(response.read().decode()).get("models", [])
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local Ollama is unavailable at 127.0.0.1:11434: {exc}") from exc
    names = {entry.get("name") for entry in models}
    names.update(entry.get("model") for entry in models)
    if model not in names and f"{model}:latest" not in names:
        raise RuntimeError(f"local Ollama does not have model {model!r}")


def command_for(spec: ClipSpec, python: Path, runner: Path, model: str,
                judge_model: str | None = None) -> list[str]:
    judge_model = judge_model or model
    return [
        str(python), str(runner),
        "--questions", str(spec.questions),
        "--gold", str(spec.gold),
        "--memory", str(spec.memory),
        "--model", model,
        "--judge-model", judge_model,
        "--checkpoint", str(spec.checkpoint),
        "--status", str(spec.status),
    ]


Invoker = Callable[[ClipSpec, list[str]], int]


def _invoke_subprocess(_spec: ClipSpec, command: list[str]) -> int:
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def run_all(specs: list[ClipSpec], model: str, python: Path, runner: Path,
            run_id: str, batch_status: Path, invoke: Invoker = _invoke_subprocess,
            judge_model: str | None = None) -> int:
    judge_model = judge_model or model
    totals = {spec.name: validate_spec(spec) for spec in specs}

    def write_batch(state: str, active: str | None, message: str) -> None:
        _atomic_json(batch_status, {
            "state": state,
            "active_clip": active,
            "order": [spec.name for spec in specs],
            "model": model,
            "answer_model": model,
            "judge_model": judge_model,
            "models_independent": model != judge_model,
            "model_runtime": "local ollama",
            "local_only": True,
            "run_id": run_id,
            "message": message,
            "updated_epoch": int(time.time()),
        })

    for position, spec in enumerate(specs, 1):
        scored = _checkpoint_rows(spec.checkpoint, totals[spec.name])
        attempted = _checkpoint_attempted(spec.checkpoint, totals[spec.name])
        if len(attempted) == totals[spec.name]:
            lane_status(spec, "complete", totals[spec.name], scored, model, run_id,
                        "checkpoint already complete; no work repeated",
                        judge_model=judge_model, queue_position=0,
                        needs_review=len(attempted) - len(scored))
        else:
            lane_status(spec, "queued", totals[spec.name], scored, model, run_id,
                        "waiting for its sequential local Gemma turn",
                        judge_model=judge_model, queue_position=position)
    write_batch("running", None, "two-clip rescore prepared")

    for spec in specs:
        total = totals[spec.name]
        if len(_checkpoint_attempted(spec.checkpoint, total)) == total:
            continue
        scored = _checkpoint_rows(spec.checkpoint, total)
        lane_status(spec, "running", total, scored, model, run_id,
                    "local Gemma answer model is running; a separate judge grades it",
                    judge_model=judge_model, queue_position=0)
        write_batch("running", spec.name, f"scoring {spec.name}; other lane remains queued")
        returncode = invoke(spec, command_for(spec, python, runner, model, judge_model))
        scored = _checkpoint_rows(spec.checkpoint, total)
        attempted = _checkpoint_attempted(spec.checkpoint, total)
        # Only a non-zero runner exit (e.g. an answer-model ERROR) or genuinely un-attempted
        # questions are fatal. A fully-attempted lane that holds a few needs_review items is
        # COMPLETE — those are excluded from the score and surfaced for human adjudication.
        if returncode != 0 or len(attempted) != total:
            reason = (f"runner exited {returncode}" if returncode != 0 else
                      f"runner stopped at {len(attempted)}/{total}")
            issues = _checkpoint_issues(spec.checkpoint, total)
            explicit = next(iter(issues.values()), None)
            lane_state = "needs_review" if explicit and explicit.get("verdict") == "needs_review" else "failed"
            lane_status(spec, lane_state, total, scored, model, run_id,
                        reason + "; checkpoint is resumable", judge_model=judge_model,
                        queue_position=0, error=reason,
                        grading_issue=explicit.get("grading") if explicit else None)
            write_batch(lane_state, spec.name, reason)
            return returncode or 2
        review_n = len(attempted) - len(scored)
        lane_status(spec, "complete", total, scored, model, run_id,
                    "all questions scored and checkpoint validated"
                    + (f"; {review_n} held for review" if review_n else ""),
                    judge_model=judge_model, queue_position=0, needs_review=review_n)

    write_batch("complete", None, "WALK and COLD checkpoints both validated complete")
    return 0


def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("another dual rescore orchestrator is already running")
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="answer model (legacy flag retained for compatibility)")
    parser.add_argument("--answer-model", default=None,
                        help="answer model; overrides --model")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL,
                        help="separate local model used only for grading")
    parser.add_argument("--order", choices=("walk,cold", "cold,walk"), default="walk,cold")
    parser.add_argument("--fresh", action="store_true",
                        help="archive both checkpoints and start a genuinely new score")
    parser.add_argument("--prepare-only", action="store_true",
                        help="validate/fingerprint inputs and publish queued lanes without scoring")
    args = parser.parse_args()
    answer_model = args.answer_model or args.model

    for role, model_name in (("answer", answer_model), ("judge", args.judge_model)):
        if not MODEL_RE.fullmatch(model_name):
            parser.error(f"only local Gemma models are allowed for {role}, got {model_name!r}")

    specs_by_name = default_specs()
    specs = [specs_by_name[name] for name in args.order.split(",")]
    run_id = time.strftime("rescore-%Y%m%d-%H%M%S")
    lock_handle = _lock(ROOT / "ops" / "cockpit" / "dual_rescore.lock")
    try:
        for spec in specs:
            total = validate_spec(spec)
            fingerprint = input_fingerprint(spec)
            prepare_checkpoint(spec, fingerprint, answer_model, fresh=args.fresh,
                               judge_model=args.judge_model)
            rows = _checkpoint_rows(spec.checkpoint, total)
            state = "complete" if len(rows) == total else "queued"
            lane_status(spec, state, total, rows, answer_model, run_id,
                        "prepared; local Gemma scoring has not started" if state == "queued"
                        else "checkpoint already complete", judge_model=args.judge_model)
        if args.prepare_only:
            _atomic_json(ROOT / "ops" / "cockpit" / "dual_rescore.json", {
                "state": "queued",
                "active_clip": None,
                "order": [spec.name for spec in specs],
                "model": answer_model,
                "answer_model": answer_model,
                "judge_model": args.judge_model,
                "models_independent": answer_model != args.judge_model,
                "model_runtime": "local ollama",
                "local_only": True,
                "run_id": run_id,
                "message": "lanes prepared; scoring not started",
                "updated_epoch": int(time.time()),
            })
            return 0
        assert_local_gemma(answer_model)
        assert_local_gemma(args.judge_model)
        python = ROOT / ".venv" / "bin" / "python"
        if not python.exists():
            python = Path(sys.executable)
        return run_all(
            specs, answer_model, python, ROOT / "evaluation" / "run_live.py", run_id,
            ROOT / "ops" / "cockpit" / "dual_rescore.json",
            judge_model=args.judge_model,
        )
    except KeyboardInterrupt:
        _atomic_json(ROOT / "ops" / "cockpit" / "dual_rescore.json", {
            "state": "interrupted", "run_id": run_id,
            "message": "stopped by user; both checkpoints remain resumable",
            "updated_epoch": int(time.time()),
        })
        return 130
    finally:
        lock_handle.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"dual rescore: {exc}", file=sys.stderr)
        raise SystemExit(2)
