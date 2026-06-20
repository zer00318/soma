from __future__ import annotations

import json
from pathlib import Path

from soma.eval.oag import calculate


def test_measured_oracle_demonstrates_answerability_from_pixels(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    scores = tmp_path / "scores.jsonl"
    oracle = tmp_path / "oracle.jsonl"

    # The gold's own annotation would call all three answerable; the measured
    # oracle proves only items 1 and 2 are actually recoverable from the frames.
    gold.write_text(
        json.dumps({"items": {"1": {"gold": "a"}, "2": {"gold": "b"}, "3": {"gold": "c"}}}),
        encoding="utf-8",
    )
    oracle.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                {"i": 1, "oracle_correct": True},
                {"i": 2, "oracle_correct": True},
                {"i": 3, "oracle_correct": False},
            ]
        ),
        encoding="utf-8",
    )
    scores.write_text(
        "\n".join(
            json.dumps(row) for row in [{"i": 1, "verdict": "correct"}, {"i": 2, "verdict": "miss"}]
        ),
        encoding="utf-8",
    )

    report = calculate(
        {
            "id": "clip",
            "split": "held_out",
            "tuning_exposure": False,
            "gold_path": str(gold),
            "score_path": str(scores),
            "oracle_path": str(oracle),
        }
    )

    assert report.oracle_mode == "measured"
    assert report.oracle_answerable == 2  # item 3 is not counted: oracle could not answer it
    assert report.text_memory_correct == 1
    assert report.answerability_gap == 1
    assert report.oag_pct == 50.0


def test_absent_oracle_path_falls_back_to_annotation(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    scores = tmp_path / "scores.jsonl"
    gold.write_text(json.dumps({"items": {"1": {"gold": "a"}}}), encoding="utf-8")
    scores.write_text(json.dumps({"i": 1, "verdict": "correct"}), encoding="utf-8")

    report = calculate(
        {"id": "c", "split": "dev", "gold_path": str(gold), "score_path": str(scores)}
    )

    assert report.oracle_mode == "annotated"
    assert report.answerability_gap == 0
