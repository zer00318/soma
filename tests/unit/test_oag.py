from __future__ import annotations

import ast
import json
from pathlib import Path

from soma.eval.oag import calculate


def test_oag_counts_every_non_correct_oracle_item_as_a_gap(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    scores = tmp_path / "scores.jsonl"
    gold.write_text(
        json.dumps(
            {
                "items": {
                    "1": {"gold": "known"},
                    "2": {"gold": "known"},
                    "3": {"unanswerable": True},
                }
            }
        ),
        encoding="utf-8",
    )
    scores.write_text(
        "\n".join(
            [json.dumps({"i": 1, "verdict": "correct"}), json.dumps({"i": 2, "verdict": "miss"})]
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
        }
    )

    assert report.oracle_answerable == 2
    assert report.answerability_gap == 1
    assert report.oag_pct == 50.0


def test_eval_package_does_not_import_engine_internals() -> None:
    eval_root = Path("src/soma/eval")
    forbidden = ("ask_home", "soma.application", "soma.adapters")
    for path in eval_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [
            node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        names = [alias.name for node in imported for alias in node.names]
        assert not any(name.startswith(forbidden) for name in names), path
