#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trace_hub.service import TraceHub


MEDIA_SUFFIXES = {".wav", ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".jpg", ".jpeg", ".png"}


def requirement(name: str, passed: bool, details: object) -> dict:
    return {"name": name, "passed": passed, "details": details}


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        hub = TraceHub(Path(temp_dir))
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:00:00+00:00",
                "source": "native_vision",
                "source_type": "vision",
                "scene_phase": "stable",
                "motion_score": 0.03,
                "memory_text": "\n".join(
                    [
                        "OBJECT | black over-ear headphones | worn on head | on visible person | likely",
                        "OBJECT | gray shirt | upper-body clothing | worn by visible person | likely",
                        "OBJECT | bottle | blue detector-tracked object; tracked for 4 detector frames | lower right frame; medium visible object; detector stream | likely",
                        'OBJECT | visible sign/board | OCR text: "Garching-Forschungszentrum" | above visible person; GPS 48.25588, 11.60994, accuracy ~35m | likely',
                        'EVENT | nearby speech | transcript: "TRACE test relation graph" | spoken near visible person | likely',
                    ]
                ),
                "location_hint": "GPS 48.25588, 11.60994, accuracy ~35m | Garching-Forschungszentrum",
            }
        )
        hub.ingest_perception(
            {
                "timestamp": "2026-06-05T10:03:00+00:00",
                "source": "native_vision",
                "source_type": "vision",
                "scene_phase": "stable",
                "memory_text": 'OBJECT | visible sign/board | OCR text: "Exit" | visible frame | likely',
                "active_entity_labels": ["visible sign/board"],
            }
        )

        graph = hub.graph_metadata()
        relations = hub.graph_relations()["relations"]
        relation_text = "\n".join(f"{row['subject']} {row['relation_type']} {row['object']}" for row in relations)
        stale_people = [row for row in graph["recent_entities"] if row["label"] == "visible person" and row["status"] == "stale"]
        media_files = [path for path in Path(temp_dir).rglob("*") if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES]

        with sqlite3.connect(Path(temp_dir) / "trace_hub.sqlite3") as conn:
            evidence_rows = conn.execute("SELECT evidence_cipher FROM graph_observations").fetchall()
        evidence_blob = "\n".join(row[0] for row in evidence_rows)

        checks = [
            requirement("relational entities exist", graph["entities"] >= 4, graph["recent_entities"]),
            requirement("worn_by relation exists", "headphones worn_by visible person" in relation_text, relation_text),
            requirement("spatial region relation exists", "bottle seen_in_frame_region lower right frame" in relation_text, relation_text),
            requirement("foreground relation exists", "bottle foreground_status medium visible object" in relation_text, relation_text),
            requirement("OCR sign relation exists", "transit sign contains_text Garching-Forschungszentrum" in relation_text, relation_text),
            requirement("place relation exists", "transit sign located_at Garching-Forschungszentrum" in relation_text, relation_text),
            requirement("stale entity tracking exists", bool(stale_people), stale_people),
            requirement("observation evidence is encrypted", "Garching-Forschungszentrum" not in evidence_blob, "encrypted evidence rows checked"),
            requirement("raw media is not persisted", not media_files, [str(path) for path in media_files]),
        ]

    print(json.dumps({"checks": checks}, indent=2))
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
