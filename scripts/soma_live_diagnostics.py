from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


NATIVE_LOG = Path.home() / "Library" / "Application Support" / "SOMA" / "soma_native_text.ndjson"
HUB_URL = "http://127.0.0.1:8765"
TOKEN = "dev-token"


def load_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def hub_json(endpoint: str) -> dict:
    request = Request(
        f"{HUB_URL}{endpoint}",
        headers={"X-SOMA-Token": TOKEN},
    )
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize_native(rows: list[dict]) -> dict:
    inference_rows = [row for row in rows if row.get("type") == "native_inference_result"]
    candidate_rows = [row for row in rows if row.get("status") == "native_vision_candidates"]
    no_record_rows = [row for row in rows if row.get("status") == "native_vision_no_record"]
    context_rows = [row for row in rows if row.get("type") == "native_context_snapshot"]

    labels = Counter()
    for row in inference_rows[-20:]:
        for label in row.get("active_entity_labels", []):
            labels[str(label)] += 1

    return {
        "native_log_exists": NATIVE_LOG.exists(),
        "total_rows": len(rows),
        "recent_inference_count": len(inference_rows[-20:]),
        "recent_candidate_count": len(candidate_rows[-20:]),
        "recent_no_record_count": len(no_record_rows[-20:]),
        "last_candidate": candidate_rows[-1] if candidate_rows else None,
        "last_inference": inference_rows[-1] if inference_rows else None,
        "last_context_snapshot": context_rows[-1] if context_rows else None,
        "recent_active_labels": labels.most_common(),
    }


def summarize_hub() -> dict:
    try:
        status = hub_json("/status")
        profiles = hub_json("/graph/profiles")
    except URLError as error:
        return {"hub_online": False, "error": str(error)}

    recent_profiles = []
    for profile in profiles.get("profiles", [])[:5]:
        recent_profiles.append(
            {
                "label": profile.get("label"),
                "status": profile.get("status"),
                "observation_count": profile.get("observation_count"),
                "canonical_summary": profile.get("canonical_summary", [])[:4],
            }
        )

    return {
        "hub_online": True,
        "graph_counts": status.get("graph", {}),
        "recent_profiles": recent_profiles,
    }


def main() -> int:
    native_rows = load_ndjson(NATIVE_LOG)
    report = {
        "native": summarize_native(native_rows),
        "hub": summarize_hub(),
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
