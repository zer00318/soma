from __future__ import annotations

from pathlib import Path

_ARCHIVE_PATH = Path(__file__).resolve().parents[2] / "archive" / "cleanup_20260625" / "trace_hub"
if not _ARCHIVE_PATH.exists():
    raise ImportError(f"trace_hub archive package is missing: {_ARCHIVE_PATH}")

__path__ = [str(_ARCHIVE_PATH)]
__all__ = ["__version__"]
__version__ = "0.1.0"

