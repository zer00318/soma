#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from evaluation import run_scene_eval
from trace_memory.adapters.live_eventlog import answer_question as eventlog_answer

CAPTURES_ROOT = ROOT / "data" / "phone_captures"
RESULTS_DIR = ROOT / "evaluation" / "results"
_SAFE = re.compile(r"[^a-zA-Z0-9_-]")
_REFUSAL_EXPECTS = {"refuse", "ocr-only-refuse", "ocr_only_refuse"}

GoldItem = run_scene_eval.GoldItem
EvalRow = run_scene_eval.EvalRow
summarize = run_scene_eval.summarize


@dataclass(frozen=True)
class CaptureTarget:
    moment: str
    db_path: Path


def _sanitize_moment(value: str) -> str:
    cleaned = _SAFE.sub("", value or "")[:64]
    return cleaned or "moment"


def _looks_like_db_path(raw: str) -> bool:
    candidate = Path(raw).expanduser()
    return candidate.suffix == ".db" or candidate.parent != Path(".") or raw.startswith(".")


def _derive_moment_from_db(db_path: Path) -> str:
    if db_path.name == "events.db" and db_path.parent.name:
        return _sanitize_moment(db_path.parent.name)
    return _sanitize_moment(db_path.stem)


def resolve_target(raw: str, *, captures_root: Path = CAPTURES_ROOT) -> CaptureTarget:
    candidate = Path(raw).expanduser()
    if candidate.exists():
        if candidate.is_dir():
            raise ValueError(f"expected an events.db file, got directory: {candidate}")
        return CaptureTarget(moment=_derive_moment_from_db(candidate), db_path=candidate)
    if _looks_like_db_path(raw):
        raise FileNotFoundError(f"events.db not found: {candidate}")

    moment = _sanitize_moment(raw)
    db_path = captures_root / moment / "events.db"
    if not db_path.exists():
        raise FileNotFoundError(f"events.db not found for moment '{moment}': {db_path}")
    return CaptureTarget(moment=moment, db_path=db_path)


def _normalize_expect(value: str) -> str:
    normalized = str(value).strip().lower()
    return "refuse" if normalized in _REFUSAL_EXPECTS else normalized


def load_gold(path: Path, *, default_moment: str) -> tuple[GoldItem, ...]:
    raw = json.loads(path.read_text())
    source_items: Any
    parent_moment = default_moment
    if isinstance(raw, dict):
        parent_moment = str(raw.get("moment") or default_moment)
        source_items = raw.get("items") or ()
    else:
        source_items = raw
    if not isinstance(source_items, list):
        raise ValueError(f"gold file must contain a list of items: {path}")

    items: list[GoldItem] = []
    for raw_item in source_items:
        if not isinstance(raw_item, dict):
            raise ValueError(f"gold items must be objects: {path}")
        must_contain = raw_item.get("must_contain") or ()
        if isinstance(must_contain, str):
            must_contain = [must_contain]
        items.append(
            GoldItem(
                moment=str(raw_item.get("moment") or parent_moment or default_moment),
                question=str(raw_item["question"]),
                expect=_normalize_expect(str(raw_item["expect"])),
                must_contain=tuple(str(token) for token in must_contain),
            )
        )
    return tuple(items)


def _ask_question(item: GoldItem, db_path: Path) -> dict[str, Any]:
    result = eventlog_answer(item.question, db_path)
    if not result.supported:
        raise ValueError(f"unsupported event-log question shape: {item.question}")
    return {
        "answer": result.answer,
        "refused": result.refused,
        "source": "eventlog",
    }


def evaluate(items: tuple[GoldItem, ...], db_path: Path) -> tuple[EvalRow, ...]:
    rows: list[EvalRow] = []
    for index, item in enumerate(items, start=1):
        result = _ask_question(item, db_path)
        answer = str(result.get("answer") or "")
        refused = bool(result.get("refused"))
        rows.append(
            EvalRow(
                index=index,
                moment=item.moment,
                question=item.question,
                expect=item.expect,
                answer=answer,
                refused=refused,
                verdict=run_scene_eval.classify_result(item, answer, refused),
            )
        )
    return tuple(rows)


def _result_paths(results_dir: Path, moment: str) -> tuple[Path, Path]:
    slug = _sanitize_moment(moment)
    return (
        results_dir / f"real_{slug}.json",
        results_dir / f"real_{slug}.md",
    )


def format_report(target: CaptureTarget, rows: tuple[EvalRow, ...]) -> str:
    summary = summarize(rows)
    correct_ci = summary["correct_ci_95"]
    hallucination_ci = summary["hallucination_ci_95"]
    lines = [
        "Real Capture Summary",
        f"moment={target.moment} events_db={target.db_path}",
        (
            f"N={summary['n']} correct%={summary['correct_pct']:.1f} "
            f"95% CI=[{correct_ci['lo']:.1f}, {correct_ci['hi']:.1f}] "
            f"hallucination%={summary['hallucination_pct']:.1f} "
            f"95% CI=[{hallucination_ci['lo']:.1f}, {hallucination_ci['hi']:.1f}]"
        ),
        f"correct={summary['correct']} wrong={summary['wrong']} hallucination={summary['hallucination']}",
        "",
        "Per-item table:",
        "idx | moment | expect | verdict | refused | question | answer",
    ]
    for row in rows:
        answer = " ".join(row.answer.split())
        lines.append(
            f"{row.index:>2} | {row.moment} | {row.expect} | {row.verdict} | "
            f"{row.refused} | {row.question} | {answer}"
        )
    return "\n".join(lines)


def _markdown_report(
    target: CaptureTarget,
    rows: tuple[EvalRow, ...],
    summary: dict[str, float | int | dict[str, float]],
) -> str:
    correct_ci = summary["correct_ci_95"]
    hallucination_ci = summary["hallucination_ci_95"]
    lines = [
        "# Real Capture Summary",
        "",
        f"- Moment: {target.moment}",
        f"- events.db: `{target.db_path}`",
        f"- N: {summary['n']}",
        (
            f"- Correct: {summary['correct']}/{summary['n']} = {summary['correct_pct']:.1f}% "
            f"(95% Wilson CI: {correct_ci['lo']:.1f}% to {correct_ci['hi']:.1f}%)"
        ),
        (
            f"- Hallucination: {summary['hallucination']}/{summary['n']} = "
            f"{summary['hallucination_pct']:.1f}% "
            f"(95% Wilson CI: {hallucination_ci['lo']:.1f}% to {hallucination_ci['hi']:.1f}%)"
        ),
        f"- Wrong: {summary['wrong']}",
        "",
        "| idx | moment | expect | verdict | refused | question | answer |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.index),
                    run_scene_eval._md_cell(row.moment),
                    run_scene_eval._md_cell(row.expect),
                    run_scene_eval._md_cell(row.verdict),
                    str(row.refused),
                    run_scene_eval._md_cell(row.question),
                    run_scene_eval._md_cell(" ".join(row.answer.split())),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_results(
    target: CaptureTarget,
    rows: tuple[EvalRow, ...],
    *,
    gold_path: Path,
    results_dir: Path = RESULTS_DIR,
) -> tuple[Path, Path]:
    summary = summarize(rows)
    json_path, md_path = _result_paths(results_dir, target.moment)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "moment": target.moment,
        "events_db": str(target.db_path),
        "gold_path": str(gold_path),
        "summary": summary,
        "rows": [
            {
                "index": row.index,
                "moment": row.moment,
                "question": row.question,
                "expect": row.expect,
                "answer": row.answer,
                "refused": row.refused,
                "verdict": row.verdict,
            }
            for row in rows
        ],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_markdown_report(target, rows, summary))
    return (json_path, md_path)


def run_real_capture(
    target: CaptureTarget,
    *,
    gold_path: Path,
) -> tuple[EvalRow, ...]:
    return evaluate(load_gold(gold_path, default_moment=target.moment), target.db_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_db_or_moment_id")
    parser.add_argument("gold")
    parser.add_argument(
        "--captures-root",
        default=str(CAPTURES_ROOT),
        help="Root directory used when the first positional argument is a moment id.",
    )
    parser.add_argument(
        "--results-dir",
        default=str(RESULTS_DIR),
        help="Directory where real_<moment>.json/.md should be written.",
    )
    args = parser.parse_args(argv)

    try:
        target = resolve_target(
            args.events_db_or_moment_id,
            captures_root=Path(args.captures_root),
        )
        gold_path = Path(args.gold)
        rows = run_real_capture(target, gold_path=gold_path)
        write_results(
            target,
            rows,
            gold_path=gold_path,
            results_dir=Path(args.results_dir),
        )
        print(format_report(target, rows))
        return 0
    except Exception as exc:
        print(f"Real Capture Summary\nHARNESS ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
