from __future__ import annotations

import json
from pathlib import Path

from evaluation import run_scene_eval


def test_scene_eval_writes_result_files_with_confidence_intervals(
    capsys,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "scene_eval_latest.json"
    md_path = tmp_path / "scene_eval_latest.md"

    result = run_scene_eval.main(
        [
            "--fixture-root",
            str(tmp_path),
            "--results-json",
            str(json_path),
            "--results-md",
            str(md_path),
        ]
    )

    captured = capsys.readouterr().out
    payload = json.loads(json_path.read_text())
    summary = payload["summary"]

    assert result == 0
    assert json_path.exists()
    assert md_path.exists()
    assert summary["n"] >= 30
    assert len(payload["rows"]) == summary["n"]
    assert summary["correct_ci_95"]["lo"] <= summary["correct_ci_95"]["hi"]
    assert summary["hallucination_ci_95"]["lo"] <= summary["hallucination_ci_95"]["hi"]
    assert "95% CI=" in captured
    assert "95% Wilson CI" in md_path.read_text()


def test_asserted_refuse_item_is_counted_as_hallucination(
    monkeypatch,
    tmp_path: Path,
) -> None:
    item = run_scene_eval.GoldItem(
        moment="pantry",
        question="is there pesto",
        expect="refuse",
    )

    monkeypatch.setattr(
        run_scene_eval.brain,
        "_ask",
        lambda payload: {
            "answer": "Yes, I saw pesto.",
            "refused": False,
            "source": "eventlog",
        },
    )

    rows = run_scene_eval.evaluate((item,), tmp_path)
    summary = run_scene_eval.summarize(rows)

    assert rows[0].verdict == "hallucination"
    assert summary["hallucination"] == 1
    assert summary["correct"] == 0
