from __future__ import annotations

from pathlib import Path

from evaluation import run_scene_eval


def test_scene_eval_fixture_prints_summary_and_table(capsys, tmp_path: Path) -> None:
    result = run_scene_eval.main(
        [
            "--fixture-root",
            str(tmp_path),
            "--results-json",
            str(tmp_path / "scene_eval_latest.json"),
            "--results-md",
            str(tmp_path / "scene_eval_latest.md"),
        ]
    )

    captured = capsys.readouterr().out

    assert result == 0
    assert "Scene Eval Summary" in captured
    assert "correct%=" in captured
    assert "hallucination%=" in captured
    assert "95% CI=" in captured
    assert "Per-item table:" in captured


def test_refuse_item_answered_is_counted_as_hallucination() -> None:
    item = run_scene_eval.GoldItem(
        moment="pantry",
        question="is there pesto",
        expect="refuse",
    )

    verdict = run_scene_eval.classify_result(item, "Yes, I saw pesto.", refused=False)

    assert verdict == "hallucination"
