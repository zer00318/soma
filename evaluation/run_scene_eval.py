#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.trace_brain_server as brain
from trace_memory.adapters.live_eventlog import append_perception_observations

GOLD_PATH = ROOT / "evaluation" / "gold" / "scene_gold.json"

_FIXTURE_RECORDS: dict[str, tuple[dict[str, Any], ...]] = {
    "pantry": (
        {
            "t": 1.0,
            "caption": "OBJECT | water bottle | blue plastic bottle | kitchen counter | likely",
            "ocr": (),
        },
        {
            "t": 2.0,
            "caption": "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
            "ocr": (),
        },
        {
            "t": 3.0,
            "caption": "OBJECT | cereal box | cardboard cereal box | pantry shelf | likely\nTEXT: MORNING OATS",
            "ocr": ("MORNING OATS",),
        },
        {
            "t": 4.0,
            "caption": "TEXT: nutella",
            "ocr": ("nutella",),
        },
    ),
    "desk": (
        {
            "t": 1.0,
            "caption": "OBJECT | coffee mug | red ceramic mug | desk | likely",
            "ocr": (),
        },
        {
            "t": 2.0,
            "caption": "OBJECT | notebook | green notebook | desk | likely",
            "ocr": (),
        },
    ),
}


@dataclass(frozen=True)
class GoldItem:
    moment: str
    question: str
    expect: str
    must_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalRow:
    index: int
    moment: str
    question: str
    expect: str
    answer: str
    refused: bool
    verdict: str


def load_gold(path: Path) -> tuple[GoldItem, ...]:
    raw_items = json.loads(path.read_text())
    items: list[GoldItem] = []
    for raw in raw_items:
        items.append(
            GoldItem(
                moment=str(raw["moment"]),
                question=str(raw["question"]),
                expect=str(raw["expect"]),
                must_contain=tuple(str(token) for token in raw.get("must_contain") or ()),
            )
        )
    return tuple(items)


def build_fixture(captures_root: Path) -> None:
    fixture_root = captures_root / "scene_eval_fixture"
    if fixture_root.exists():
        shutil.rmtree(fixture_root)
    fixture_root.mkdir(parents=True, exist_ok=True)

    for moment, records in _FIXTURE_RECORDS.items():
        moment_dir = fixture_root / moment
        moment_dir.mkdir(parents=True, exist_ok=True)
        db_path = moment_dir / "events.db"
        kf_rows: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            t_seconds = float(record["t"])
            caption = str(record["caption"])
            ocr_lines = tuple(str(line) for line in record.get("ocr") or ())
            append_perception_observations(
                db_path,
                moment_id=moment,
                t_seconds=t_seconds,
                memory_text=caption,
                ocr_lines=ocr_lines,
            )
            kf_rows.append(
                {
                    "t": t_seconds,
                    "frame": f"f_{index}",
                    "caption": caption,
                    "ocr": list(ocr_lines),
                    "source": "scene_eval_fixture",
                }
            )
        (moment_dir / "kf_memory.json").write_text(json.dumps(kf_rows, indent=2))


@contextmanager
def configured_eventlog_brain(captures_root: Path) -> Iterator[None]:
    previous_captures = brain.CAPTURES
    previous_trace_eventlog = brain.TRACE_EVENTLOG
    brain.CAPTURES = captures_root / "scene_eval_fixture"
    brain.TRACE_EVENTLOG = True
    brain._LIVE.clear()
    try:
        yield
    finally:
        brain.CAPTURES = previous_captures
        brain.TRACE_EVENTLOG = previous_trace_eventlog
        brain._LIVE.clear()


def classify_result(item: GoldItem, answer: str, refused: bool) -> str:
    if item.expect == "refuse":
        return "correct" if refused else "hallucination"
    if refused:
        return "wrong"
    lowered_answer = answer.lower()
    required = [token.lower() for token in item.must_contain]
    return "correct" if all(token in lowered_answer for token in required) else "wrong"


def ask_question(item: GoldItem) -> dict[str, Any]:
    return brain._ask({"moment_id": item.moment, "question": item.question})


def evaluate(items: tuple[GoldItem, ...], captures_root: Path) -> tuple[EvalRow, ...]:
    rows: list[EvalRow] = []
    with configured_eventlog_brain(captures_root):
        for index, item in enumerate(items, start=1):
            result = ask_question(item)
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
                    verdict=classify_result(item, answer, refused),
                )
            )
    return tuple(rows)


def summarize(rows: tuple[EvalRow, ...]) -> dict[str, float | int]:
    total = len(rows)
    correct = sum(row.verdict == "correct" for row in rows)
    wrong = sum(row.verdict == "wrong" for row in rows)
    hallucination = sum(row.verdict == "hallucination" for row in rows)
    return {
        "n": total,
        "correct": correct,
        "wrong": wrong,
        "hallucination": hallucination,
        "correct_pct": round((correct / total) * 100, 1) if total else 0.0,
        "hallucination_pct": round((hallucination / total) * 100, 1) if total else 0.0,
    }


def format_report(rows: tuple[EvalRow, ...]) -> str:
    summary = summarize(rows)
    lines = [
        "Scene Eval Summary",
        f"N={summary['n']} correct%={summary['correct_pct']:.1f} hallucination%={summary['hallucination_pct']:.1f}",
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


def run_scene_eval(*, gold_path: Path = GOLD_PATH, captures_root: Path | None = None) -> tuple[EvalRow, ...]:
    if captures_root is None:
        with tempfile.TemporaryDirectory(prefix="scene-eval-") as directory:
            temp_root = Path(directory)
            build_fixture(temp_root)
            return evaluate(load_gold(gold_path), temp_root)
    build_fixture(captures_root)
    return evaluate(load_gold(gold_path), captures_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default=str(GOLD_PATH))
    parser.add_argument(
        "--fixture-root",
        default=None,
        help="Directory where the offline fixture capture should be built.",
    )
    args = parser.parse_args(argv)

    try:
        captures_root = Path(args.fixture_root) if args.fixture_root else None
        rows = run_scene_eval(gold_path=Path(args.gold), captures_root=captures_root)
        print(format_report(rows))
    except Exception as exc:
        print(f"Scene Eval Summary\nHARNESS ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
