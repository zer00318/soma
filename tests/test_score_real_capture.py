from __future__ import annotations

import json
from pathlib import Path

from evaluation import score_real_capture
from trace_memory.adapters.live_eventlog import EventLogAnswer, append_perception_observations


def _build_fixture_db(capture_dir: Path) -> Path:
    capture_dir.mkdir(parents=True, exist_ok=True)
    db_path = capture_dir / "events.db"
    append_perception_observations(
        db_path,
        moment_id="pantry_capture",
        t_seconds=1.0,
        memory_text="OBJECT | water bottle | blue plastic bottle | left shelf | likely",
        ocr_lines=(),
    )
    append_perception_observations(
        db_path,
        moment_id="pantry_capture",
        t_seconds=2.0,
        memory_text="OBJECT | water bottle | silver sports bottle | right shelf | likely",
        ocr_lines=(),
    )
    append_perception_observations(
        db_path,
        moment_id="pantry_capture",
        t_seconds=3.0,
        memory_text=(
            "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely"
        ),
        ocr_lines=("Pringles",),
    )
    append_perception_observations(
        db_path,
        moment_id="pantry_capture",
        t_seconds=4.0,
        memory_text=(
            "OBJECT | cereal box | cardboard cereal box | pantry shelf | likely\n"
            "TEXT: MORNING OATS"
        ),
        ocr_lines=("MORNING OATS",),
    )
    append_perception_observations(
        db_path,
        moment_id="pantry_capture",
        t_seconds=5.0,
        memory_text="TEXT: nutella",
        ocr_lines=("nutella",),
    )
    return db_path


def _write_gold(path: Path) -> None:
    payload = {
        "moment": "pantry_capture",
        "items": [
            {
                "question": "is there a water bottle",
                "expect": "answer",
                "must_contain": ["yes", "water bottle"],
            },
            {
                "question": "how many water bottles",
                "expect": "count",
                "must_contain": ["2", "water bottle"],
            },
            {
                "question": "what flavour is the pringles",
                "expect": "answer",
                "must_contain": ["sour cream and onion"],
            },
            {
                "question": "what text is on the cereal box",
                "expect": "read",
                "must_contain": ["morning oats"],
            },
            {
                "question": "how many nutella jars",
                "expect": "ocr-only-refuse",
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def test_score_real_capture_writes_result_files_with_confidence_intervals(
    capsys,
    tmp_path: Path,
) -> None:
    capture_dir = tmp_path / "pantry_capture"
    db_path = _build_fixture_db(capture_dir)
    gold_path = tmp_path / "gold.json"
    results_dir = tmp_path / "results"
    _write_gold(gold_path)

    result = score_real_capture.main(
        [
            str(db_path),
            str(gold_path),
            "--results-dir",
            str(results_dir),
        ]
    )

    captured = capsys.readouterr().out
    json_path = results_dir / "real_pantry_capture.json"
    md_path = results_dir / "real_pantry_capture.md"
    payload = json.loads(json_path.read_text())
    summary = payload["summary"]

    assert result == 0
    assert json_path.exists()
    assert md_path.exists()
    assert summary["n"] == 5
    assert len(payload["rows"]) == summary["n"]
    assert summary["correct_ci_95"]["lo"] <= summary["correct_ci_95"]["hi"]
    assert summary["hallucination_ci_95"]["lo"] <= summary["hallucination_ci_95"]["hi"]
    assert "correct%=" in captured
    assert "hallucination%=" in captured
    assert "95% Wilson CI" in md_path.read_text()


def test_asserted_refuse_item_is_counted_as_hallucination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    item = score_real_capture.GoldItem(
        moment="pantry_capture",
        question="is there pesto",
        expect="refuse",
    )

    monkeypatch.setattr(
        score_real_capture,
        "eventlog_answer",
        lambda question, db_path: EventLogAnswer(
            supported=True,
            answer="Yes, I saw pesto.",
            refused=False,
            citations=(),
        ),
    )

    rows = score_real_capture.evaluate((item,), tmp_path / "events.db")
    summary = score_real_capture.summarize(rows)

    assert rows[0].verdict == "hallucination"
    assert summary["hallucination"] == 1
    assert summary["correct"] == 0
