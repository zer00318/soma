from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OagReport:
    dataset_id: str
    split: str
    tuning_exposure: bool
    oracle_answerable: int
    text_memory_correct: int
    answerability_gap: int
    oag_pct: float
    missing_grades: int
    unresolved_grades: int
    complete: bool


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}: every line must be a JSON object")
            rows.append(value)
    return rows


def _oracle_ids(gold_path: Path) -> set[int]:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    items = gold.get("items")
    if not isinstance(items, dict):
        raise ValueError(f"{gold_path}: items must be an object")
    return {int(item_id) for item_id, item in items.items() if _oracle_can_answer(item)}


def _oracle_can_answer(item: object) -> bool:
    if not isinstance(item, dict):
        raise ValueError("gold items must be objects")
    return bool(item.get("oracle_answerable", not item.get("unanswerable", False)))


def calculate(dataset: dict[str, Any]) -> OagReport:
    oracle_ids = _oracle_ids(Path(str(dataset["gold_path"])))
    latest = {int(row["i"]): row for row in _read_jsonl(Path(str(dataset["score_path"])))}
    correct = sum(latest.get(item_id, {}).get("verdict") == "correct" for item_id in oracle_ids)
    missing = sum(item_id not in latest for item_id in oracle_ids)
    unresolved = sum(
        latest.get(item_id, {}).get("verdict") not in {"correct", "wrong", "miss"}
        for item_id in oracle_ids
        if item_id in latest
    )
    gap = len(oracle_ids) - correct
    oag_pct = round(100.0 * gap / len(oracle_ids), 1) if oracle_ids else 0.0
    return OagReport(
        dataset_id=str(dataset["id"]),
        split=str(dataset["split"]),
        tuning_exposure=bool(dataset.get("tuning_exposure", True)),
        oracle_answerable=len(oracle_ids),
        text_memory_correct=correct,
        answerability_gap=gap,
        oag_pct=oag_pct,
        missing_grades=missing,
        unresolved_grades=unresolved,
        complete=missing == 0 and unresolved == 0,
    )


def calculate_manifest(path: Path) -> list[OagReport]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("manifest datasets must be a list")
    return [calculate(dataset) for dataset in datasets]


def _render(reports: Iterable[OagReport]) -> str:
    return json.dumps({"reports": [asdict(report) for report in reports]}, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute the oracle-answerability gap")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(_render(calculate_manifest(args.manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
