from __future__ import annotations

import json
from pathlib import Path

from soma.eval.gold_lock import freeze, verify


def _write_gold(path: Path, n: int) -> None:
    path.write_text(
        json.dumps({"items": {str(i): {"gold": f"a{i}"} for i in range(1, n + 1)}}),
        encoding="utf-8",
    )


def _ras(root: Path) -> Path:
    ras = root / "evaluation" / "ras"
    ras.mkdir(parents=True)
    return ras


def test_freeze_then_verify_is_clean(tmp_path: Path) -> None:
    ras = _ras(tmp_path)
    _write_gold(ras / "walk.gold.json", 3)
    lock_path = tmp_path / "gold.lock.json"
    lock_path.write_text(json.dumps(freeze(tmp_path)) + "\n", encoding="utf-8")

    assert verify(tmp_path, lock_path) == []


def test_verify_flags_a_silently_edited_gold(tmp_path: Path) -> None:
    ras = _ras(tmp_path)
    gold = ras / "walk.gold.json"
    _write_gold(gold, 3)
    lock_path = tmp_path / "gold.lock.json"
    lock_path.write_text(json.dumps(freeze(tmp_path)) + "\n", encoding="utf-8")

    _write_gold(gold, 4)  # loosen the key after freezing
    violations = verify(tmp_path, lock_path)

    assert len(violations) == 1
    assert violations[0].startswith("CHANGED")


def test_verify_flags_a_new_unpinned_gold(tmp_path: Path) -> None:
    ras = _ras(tmp_path)
    _write_gold(ras / "walk.gold.json", 2)
    lock_path = tmp_path / "gold.lock.json"
    lock_path.write_text(json.dumps(freeze(tmp_path)) + "\n", encoding="utf-8")

    _write_gold(ras / "second.gold.json", 2)  # appears after the freeze
    violations = verify(tmp_path, lock_path)

    assert any(v.startswith("UNFROZEN") for v in violations)


def test_freeze_requires_at_least_one_gold(tmp_path: Path) -> None:
    _ras(tmp_path)
    try:
        freeze(tmp_path)
    except ValueError:
        return
    raise AssertionError("freeze must reject an empty gold set")
