from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    datasets = value.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError("manifest datasets must be a list")
    return datasets


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = Path(sys.argv[1])
    failures: list[str] = []
    for dataset in load_manifest(manifest):
        gold_path = Path(str(dataset["gold_path"]))
        expected = str(dataset["sha256"])
        actual = digest(gold_path)
        if actual != expected:
            failures.append(f"{gold_path}: expected {expected}, got {actual}")
        score_path = Path(str(dataset["score_path"]))
        score_expected = str(dataset["score_sha256"])
        score_actual = digest(score_path)
        if score_actual != score_expected:
            failures.append(f"{score_path}: expected {score_expected}, got {score_actual}")
    if failures:
        print("Frozen gold changed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"frozen-gold: {len(load_manifest(manifest))} files verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
