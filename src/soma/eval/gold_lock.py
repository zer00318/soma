"""Tamper-evident freeze for the evaluation gold keys.

The cardinal eval sin is letting the answer key drift toward the engine while the
same party tunes both. This module pins every gold file by content hash into a
lock file. ``verify`` fails if any pinned gold changed, vanished, or if a new
gold appeared unpinned -- so a gold edit becomes a deliberate, reviewable
``freeze`` (with a recorded reason) instead of a silent score inflation.

Stdlib only and engine-agnostic by design: the eval layer must never import the
thing it grades (enforced by tests/unit/test_oag.py).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

LOCK_VERSION = 1
DEFAULT_GLOB = "evaluation/ras/*.gold.json"
DEFAULT_LOCK = "evaluation/gold.lock.json"


@dataclass(frozen=True)
class GoldEntry:
    path: str
    sha256: str
    n_items: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _n_items(path: Path) -> int:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    items = doc.get("items") if isinstance(doc, dict) else None
    return len(items) if isinstance(items, dict) else 0


def _discover(root: Path, glob: str) -> list[Path]:
    return sorted(root.glob(glob))


def freeze(root: Path, glob: str = DEFAULT_GLOB, note: str = "") -> dict[str, object]:
    """Pin every gold matched by ``glob`` (relative to ``root``) into a lock dict."""
    entries = [
        GoldEntry(path=str(path.relative_to(root)), sha256=_sha256(path), n_items=_n_items(path))
        for path in _discover(root, glob)
    ]
    if not entries:
        raise ValueError(f"no gold files matched {glob!r} under {root}")
    return {
        "version": LOCK_VERSION,
        "glob": glob,
        "frozen_at_ms": time.time_ns() // 1_000_000,
        "note": note,
        "entries": [asdict(entry) for entry in entries],
    }


def verify(root: Path, lock_path: Path) -> list[str]:
    """Return a list of human-readable integrity violations (empty means clean)."""
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("version") != LOCK_VERSION:
        return [f"lock version {lock.get('version')} != supported {LOCK_VERSION}"]

    pinned = {entry["path"]: entry for entry in lock.get("entries", [])}
    violations: list[str] = []
    for rel, entry in pinned.items():
        path = root / rel
        if not path.exists():
            violations.append(f"MISSING: pinned gold {rel} no longer exists")
            continue
        actual = _sha256(path)
        if actual != entry["sha256"]:
            violations.append(
                f"CHANGED: {rel} hash {actual[:12]} != pinned {entry['sha256'][:12]} "
                "(re-freeze with --note if this edit is intended)"
            )

    glob = str(lock.get("glob", DEFAULT_GLOB))
    for path in _discover(root, glob):
        rel = str(path.relative_to(root))
        if rel not in pinned:
            violations.append(f"UNFROZEN: new gold {rel} is not pinned -- run freeze")
    return violations


def _do_freeze(root: Path, lock_path: Path, glob: str, note: str) -> int:
    lock = freeze(root, glob=glob, note=note)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    n = len(lock["entries"]) if isinstance(lock["entries"], list) else 0
    print(f"froze {n} gold file(s) into {lock_path}")
    return 0


def _do_verify(root: Path, lock_path: Path) -> int:
    if not lock_path.exists():
        print(f"no lock at {lock_path} -- run `freeze` first")
        return 2
    violations = verify(root, lock_path)
    if violations:
        print("GOLD INTEGRITY FAILED:")
        for line in violations:
            print(f"  - {line}")
        return 1
    print("gold integrity OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze/verify evaluation gold keys")
    parser.add_argument("command", choices=["freeze", "verify"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--glob", default=DEFAULT_GLOB)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    lock_path = Path(args.lock) if args.lock else root / DEFAULT_LOCK
    if args.command == "freeze":
        return _do_freeze(root, lock_path, str(args.glob), str(args.note))
    return _do_verify(root, lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
