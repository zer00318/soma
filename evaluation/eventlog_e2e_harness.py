from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import scripts.trace_brain_server as brain
from trace_memory.adapters.live_eventlog import HONEST_REFUSAL


@dataclass(frozen=True)
class BatteryRow:
    key: str
    question: str
    passed: bool
    answer: str
    refused: bool
    source: str
    citations: tuple[dict[str, Any], ...]
    personal_evidence: str
    world_context: str
    detail: str


@dataclass(frozen=True)
class EventLogE2ERun:
    captures_root: Path
    moment_id: str
    db_path: Path
    rows: tuple[BatteryRow, ...]


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self._now = start

    def time(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _fake_world_oracle(prompt: str) -> str:
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


def _capture_payload(
    memory_text: str,
    *,
    moment_id: str,
    yaw_degrees: float | None = None,
    source: str = "native_vision",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "moment_id": moment_id,
        "source": source,
        "location_hint": "Kitchen pantry",
        "memory_text": memory_text,
    }
    if yaw_degrees is not None:
        payload["metadata"] = {
            "pose": {
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "pitch": 0.0,
                "roll": 0.0,
                "yaw": math.radians(yaw_degrees),
            }
        }
    return payload


@contextmanager
def configured_eventlog_brain(captures_root: Path) -> Iterator[_FakeClock]:
    previous_captures = brain.CAPTURES
    previous_trace_eventlog = brain.TRACE_EVENTLOG
    previous_world_oracle = brain._eventlog_world_knowledge_oracle
    previous_log = brain._log
    previous_time = brain.time.time
    clock = _FakeClock()
    brain.CAPTURES = captures_root
    brain.TRACE_EVENTLOG = True
    brain._eventlog_world_knowledge_oracle = _fake_world_oracle
    brain._log = lambda *_args, **_kwargs: None
    brain.time.time = clock.time
    brain._LIVE.clear()
    try:
        yield clock
    finally:
        brain.CAPTURES = previous_captures
        brain.TRACE_EVENTLOG = previous_trace_eventlog
        brain._eventlog_world_knowledge_oracle = previous_world_oracle
        brain._log = previous_log
        brain.time.time = previous_time
        brain._LIVE.clear()


def _ask(moment_id: str, question: str) -> dict[str, Any]:
    return brain._ask({"moment_id": moment_id, "question": question})


def _row(
    key: str,
    question: str,
    result: dict[str, Any],
    *,
    passed: bool,
    detail: str,
) -> BatteryRow:
    return BatteryRow(
        key=key,
        question=question,
        passed=passed,
        answer=str(result.get("answer") or ""),
        refused=bool(result.get("refused")),
        source=str(result.get("source") or ""),
        citations=tuple(result.get("citations") or ()),
        personal_evidence=str(result.get("personal_evidence") or ""),
        world_context=str(result.get("world_context") or ""),
        detail=detail,
    )


def run_battery(captures_root: Path, *, moment_id: str = "live") -> EventLogE2ERun:
    captures_root.mkdir(parents=True, exist_ok=True)
    with configured_eventlog_brain(captures_root) as clock:
        brain._capture(
            _capture_payload(
                "\n".join(
                    [
                        "OBJECT | water bottle | clear reusable bottle | counter edge | likely",
                        "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
                        "OBJECT | soda can | chilled aluminium can | back shelf | likely",
                        "TEXT: Pringles | CLUB SODA | nutella",
                    ]
                ),
                moment_id=moment_id,
                yaw_degrees=0.0,
            )
        )
        clock.advance(0.4)
        brain._capture(
            _capture_payload(
                "OBJECT | water bottle | clear reusable bottle | counter edge | likely",
                moment_id=moment_id,
                yaw_degrees=40.0,
            )
        )

        present_question = "is there a water bottle"
        present = _ask(moment_id, present_question)

        count_question = "how many water bottles"
        count = _ask(moment_id, count_question)

        flavour_question = "what flavour is the pringles"
        flavour = _ask(moment_id, flavour_question)

        absent_question = "is there pesto"
        absent = _ask(moment_id, absent_question)

        ocr_only_question = "how many nutella jars"
        ocr_only = _ask(moment_id, ocr_only_question)

        clock.advance(0.6)
        brain._capture(
            _capture_payload(
                "\n".join(
                    [
                        "OBJECT | stairs | wooden staircase | hallway | likely",
                        "OBJECT | window | open glass window | living room wall | likely",
                    ]
                ),
                moment_id=moment_id,
                yaw_degrees=None,
            )
        )
        persistent = _ask(moment_id, flavour_question)

    rows = (
        _row(
            "present_object",
            present_question,
            present,
            passed=(
                present.get("source") == "eventlog"
                and not present.get("refused")
                and bool(present.get("citations"))
                and bool(present.get("personal_evidence"))
                and "water bottle" in str(present.get("answer") or "").lower()
            ),
            detail=(
                f"source={present.get('source')} citations={len(present.get('citations') or ())} "
                f"personal_evidence={bool(present.get('personal_evidence'))}"
            ),
        ),
        _row(
            "duplicate_across_poses",
            count_question,
            count,
            passed=(
                count.get("source") == "eventlog"
                and not count.get("refused")
                and len(count.get("citations") or ()) >= 2
                and (
                    "2 water bottles" in str(count.get("answer") or "").lower()
                    or "at least 2 water bottles" in str(count.get("answer") or "").lower()
                )
            ),
            detail=f"answer={str(count.get('answer') or '').strip()}",
        ),
        _row(
            "flavour_read",
            flavour_question,
            flavour,
            passed=(
                flavour.get("source") == "eventlog"
                and not flavour.get("refused")
                and str(flavour.get("world_context") or "").startswith("```world_context\n")
                and "sour cream and onion" in str(flavour.get("answer") or "").lower()
                and "pringles is a brand of stackable potato crisps." in str(flavour.get("world_context") or "").lower()
            ),
            detail="world_context fenced with grounded flavour answer",
        ),
        _row(
            "absent_thing",
            absent_question,
            absent,
            passed=(
                absent.get("source") == "eventlog"
                and bool(absent.get("refused"))
                and str(absent.get("answer") or "") == HONEST_REFUSAL
            ),
            detail=f"refused={absent.get('refused')} answer={absent.get('answer')}",
        ),
        _row(
            "ocr_only_term",
            ocr_only_question,
            ocr_only,
            passed=(
                ocr_only.get("source") == "eventlog"
                and bool(ocr_only.get("refused"))
                and str(ocr_only.get("answer") or "") == HONEST_REFUSAL
            ),
            detail=f"refused={ocr_only.get('refused')} answer={ocr_only.get('answer')}",
        ),
        _row(
            "persistence_after_second_capture",
            flavour_question,
            persistent,
            passed=(
                persistent.get("source") == "eventlog"
                and not persistent.get("refused")
                and "sour cream and onion" in str(persistent.get("answer") or "").lower()
                and str(persistent.get("world_context") or "").startswith("```world_context\n")
            ),
            detail="after unrelated capture, the first scene's flavour answer still resolves",
        ),
    )
    return EventLogE2ERun(
        captures_root=captures_root,
        moment_id=moment_id,
        db_path=captures_root / moment_id / "events.db",
        rows=rows,
    )


def format_results_table(run: EventLogE2ERun) -> str:
    lines = [
        "Event-log E2E Battery",
        f"events_db: {run.db_path}",
        "",
        "| check | question | status | detail |",
        "| --- | --- | --- | --- |",
    ]
    for row in run.rows:
        status = "PASS" if row.passed else "FAIL"
        detail = row.detail.replace("\n", " ").replace("|", "\\|")
        question = row.question.replace("|", "\\|")
        lines.append(f"| {row.key} | {question} | {status} | {detail} |")
    return "\n".join(lines)


def all_passed(run: EventLogE2ERun) -> bool:
    return all(row.passed for row in run.rows)
