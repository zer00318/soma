#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.trace_brain_server as brain
from trace_memory.adapters.live_eventlog import append_perception_observations

GOLD_PATH = ROOT / "evaluation" / "gold" / "scene_gold.json"
RESULTS_JSON_PATH = ROOT / "evaluation" / "results" / "scene_eval_latest.json"
RESULTS_MD_PATH = ROOT / "evaluation" / "results" / "scene_eval_latest.md"


def _record(
    t_seconds: float,
    caption: str,
    *,
    ocr: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {"t": t_seconds, "caption": caption, "ocr": ocr}


_FIXTURE_RECORDS: dict[str, tuple[dict[str, Any], ...]] = {
    "pantry": (
        _record(
            1.0,
            "OBJECT | water bottle | blue plastic bottle | kitchen counter | likely",
        ),
        _record(
            2.0,
            "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
            ocr=("Pringles",),
        ),
        _record(
            3.0,
            "OBJECT | cereal box | cardboard cereal box | pantry shelf | likely\nTEXT: MORNING OATS",
            ocr=("MORNING OATS",),
        ),
        _record(4.0, "TEXT: nutella", ocr=("nutella",)),
        _record(
            5.0,
            "OBJECT | soda can | chilled aluminium can | back shelf | likely\nTEXT: CLUB SODA",
            ocr=("CLUB SODA",),
        ),
    ),
    "desk": (
        _record(
            1.0,
            "OBJECT | coffee mug | red ceramic mug | left desk | likely",
        ),
        _record(
            2.0,
            "OBJECT | notebook | green notebook | center desk | likely",
        ),
        _record(
            3.0,
            "OBJECT | coffee mug | white ceramic mug | right desk | likely",
        ),
        _record(
            4.0,
            "OBJECT | tea tin | metal tea tin | back desk | likely\nTEXT: EARL GREY",
            ocr=("EARL GREY",),
        ),
        _record(
            5.0,
            "OBJECT | pen cup | black pen cup | front desk | likely",
        ),
    ),
    "fridge": (
        _record(
            1.0,
            "OBJECT | water bottle | clear reusable bottle | left shelf | likely",
        ),
        _record(
            1.4,
            "OBJECT | water bottle | clear reusable bottle | left shelf | likely",
        ),
        _record(
            2.0,
            "OBJECT | water bottle | silver sports bottle | right shelf | likely",
        ),
        _record(
            2.4,
            "OBJECT | water bottle | silver sports bottle | right shelf | likely",
        ),
        _record(
            3.0,
            "OBJECT | yogurt cup | blueberry yogurt cup | middle shelf | likely",
        ),
        _record(
            4.0,
            "OBJECT | juice carton | orange juice carton | door shelf | likely\nTEXT: SUNVALE ORANGE",
            ocr=("SUNVALE ORANGE",),
        ),
    ),
    "sideboard": (
        _record(
            1.0,
            "OBJECT | candle jar | blue glass candle jar | left sideboard | likely",
        ),
        _record(
            1.6,
            "OBJECT | candle jar | blue glass candle jar | left sideboard | likely",
        ),
        _record(
            2.4,
            "OBJECT | candle jar | blue glass candle jar | right sideboard | likely",
        ),
        _record(
            3.0,
            "OBJECT | book | hardback travel book | center table | likely\nTEXT: CITY WALKS",
            ocr=("CITY WALKS",),
        ),
        _record(
            4.0,
            "OBJECT | cracker box | flavour: rosemary | coffee table | likely",
        ),
        _record(
            5.0,
            "OBJECT | apple | red apple | fruit bowl | likely",
        ),
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


def _scene_eval_world_oracle(prompt: str) -> str:
    lowered = prompt.lower()
    if "first line exactly: yes or no" in lowered:
        return "YES" if "pringles" in lowered else "NO"
    if "pringles" in lowered:
        return (
            "KIND: product\n"
            "CONF: 0.94\n"
            "GLOSS: Pringles is a brand of stackable potato crisps."
        )
    return "UNKNOWN"


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
    previous_world_oracle = brain._eventlog_world_knowledge_oracle
    brain.CAPTURES = captures_root / "scene_eval_fixture"
    brain.TRACE_EVENTLOG = True
    brain._eventlog_world_knowledge_oracle = _scene_eval_world_oracle
    brain._LIVE.clear()
    try:
        yield
    finally:
        brain.CAPTURES = previous_captures
        brain.TRACE_EVENTLOG = previous_trace_eventlog
        brain._eventlog_world_knowledge_oracle = previous_world_oracle
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


def _wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    phat = successes / total
    z2 = z * z
    denominator = 1.0 + (z2 / total)
    center = (phat + (z2 / (2.0 * total))) / denominator
    margin = (
        z
        * math.sqrt((phat * (1.0 - phat) / total) + (z2 / (4.0 * total * total)))
        / denominator
    )
    lo = max(0.0, center - margin) * 100.0
    hi = min(1.0, center + margin) * 100.0
    return (round(lo, 1), round(hi, 1))


def summarize(rows: tuple[EvalRow, ...]) -> dict[str, float | int | dict[str, float]]:
    total = len(rows)
    correct = sum(row.verdict == "correct" for row in rows)
    wrong = sum(row.verdict == "wrong" for row in rows)
    hallucination = sum(row.verdict == "hallucination" for row in rows)
    correct_ci = _wilson_ci(correct, total)
    hallucination_ci = _wilson_ci(hallucination, total)
    return {
        "n": total,
        "correct": correct,
        "wrong": wrong,
        "hallucination": hallucination,
        "correct_pct": round((correct / total) * 100, 1) if total else 0.0,
        "hallucination_pct": round((hallucination / total) * 100, 1) if total else 0.0,
        "correct_ci_95": {"lo": correct_ci[0], "hi": correct_ci[1]},
        "hallucination_ci_95": {"lo": hallucination_ci[0], "hi": hallucination_ci[1]},
    }


def format_report(rows: tuple[EvalRow, ...]) -> str:
    summary = summarize(rows)
    correct_ci = summary["correct_ci_95"]
    hallucination_ci = summary["hallucination_ci_95"]
    lines = [
        "Scene Eval Summary",
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


def write_results(
    rows: tuple[EvalRow, ...],
    *,
    json_path: Path = RESULTS_JSON_PATH,
    md_path: Path = RESULTS_MD_PATH,
) -> None:
    summary = summarize(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
    md_path.write_text(_markdown_report(rows, summary))


def _markdown_report(
    rows: tuple[EvalRow, ...],
    summary: dict[str, float | int | dict[str, float]],
) -> str:
    correct_ci = summary["correct_ci_95"]
    hallucination_ci = summary["hallucination_ci_95"]
    lines = [
        "# Scene Eval Summary",
        "",
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
                    _md_cell(row.moment),
                    _md_cell(row.expect),
                    _md_cell(row.verdict),
                    str(row.refused),
                    _md_cell(row.question),
                    _md_cell(" ".join(row.answer.split())),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|")


def run_scene_eval(
    *,
    gold_path: Path = GOLD_PATH,
    captures_root: Path | None = None,
) -> tuple[EvalRow, ...]:
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
    parser.add_argument("--results-json", default=str(RESULTS_JSON_PATH))
    parser.add_argument("--results-md", default=str(RESULTS_MD_PATH))
    args = parser.parse_args(argv)

    try:
        captures_root = Path(args.fixture_root) if args.fixture_root else None
        rows = run_scene_eval(gold_path=Path(args.gold), captures_root=captures_root)
        write_results(
            rows,
            json_path=Path(args.results_json),
            md_path=Path(args.results_md),
        )
        print(format_report(rows))
        return 0
    except Exception as exc:
        print(f"Scene Eval Summary\nHARNESS ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
