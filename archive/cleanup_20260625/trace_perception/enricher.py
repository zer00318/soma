"""Enrichment consumer: crop + level → local VLM → delta facts in the graph.

Watches the worker's file queue (/tmp/trace_enrich) for crop/sidecar pairs and
runs the level-appropriate vision pass on local gemma3 (multimodal, via
ollama). Level 1 records an overview; levels 2-3 are DELTA passes — the
prompt includes what the graph already knows and asks only for new detail
(attributes, then minutiae: wear, scratches, peeling, unique marks).

In-process graph writes, no server — matches the phone-library architecture.

    .venv/bin/python -m trace_perception.enricher --db data/trace_hub.sqlite3
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path

from trace_hub.crypto import EncryptedTextCodec
from trace_hub.graph import RelationalMemoryGraph

_MODEL = "gemma3:12b-it-qat"
_OLLAMA = "http://localhost:11434/api/generate"

_PROMPTS = {
    "overview": (
        "Describe this {label} in 1-2 short sentences: what it is, main "
        "colors, and the most notable visible feature. Only what you can "
        "actually see — no guesses."
    ),
    "attributes": (
        "Already recorded about this {label}: \"{known}\". "
        "List ONLY NEW visible details not yet recorded: material, condition, "
        "any readable text or logos, shape details, accessories. Short "
        "phrases separated by semicolons. Material and brand are often NOT "
        "determinable from an image: say e.g. 'material: glass or glossy "
        "plastic (uncertain)' or omit it — a confident wrong material is "
        "worse than none (walk-1: glass iPhone recorded as plastic). "
        "If nothing new is visible, answer exactly: nothing new."
    ),
    "minutiae": (
        "Already recorded about this {label}: \"{known}\". "
        "Look for fine identifying details ONLY: scratches, paint peeling, "
        "stains, wear marks, dents, stickers, unique blemishes and their "
        "locations. Short phrases separated by semicolons. If none are "
        "visible, answer exactly: nothing new."
    ),
}


def _vlm_describe(image_path: Path, prompt: str, timeout: int = 60) -> str:
    payload = json.dumps(
        {
            "model": _MODEL,
            "prompt": prompt,
            "images": [base64.b64encode(image_path.read_bytes()).decode()],
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode()
    req = urllib.request.Request(
        _OLLAMA, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("response", "").strip()


class Enricher:
    def __init__(self, graph: RelationalMemoryGraph, queue_dir: Path) -> None:
        self.graph = graph
        self.queue_dir = queue_dir
        # track_id (per worker session) → graph entity id
        self._entity_by_track: dict[str, str] = {}

    def _resolve_entity(self, meta: dict) -> str:
        track_id = str(meta["track_id"])
        if track_id in self._entity_by_track:
            return self._entity_by_track[track_id]
        # Establish the entity through the normal perception ingest path so
        # dedup/confidence gates apply, then remember the mapping.
        memory_text = (
            f"OBJECT | visible {meta['label']} | detector-tracked "
            f"{meta['label']}; mostly {meta.get('color', 'unknown')} | "
            f"{meta.get('frame_position', 'unknown')}; enrichment subject | likely"
        )
        self.graph.ingest_packet(
            {
                "memory_text": memory_text,
                "captured_at": meta.get("captured_at"),
                "source_type": "vision",
                "provider": "enrichment_scheduler",
                "confidence": 0.75,
            }
        )
        # ingest_packet returns counts; resolve the id via the freshest
        # matching entity (profiles orders current-first, last_seen DESC).
        prof = self.graph.profiles(label=meta["label"], limit=1).get("profiles", [])
        entity_id = prof[0]["id"] if prof else ""
        if entity_id:
            self._entity_by_track[track_id] = entity_id
        return entity_id

    def _known_so_far(self, entity_id: str) -> str:
        parts = []
        for focus in ("overview", "attributes"):
            val = self.graph.get_entity_attribute(entity_id, f"vlm_{focus}")
            if val:
                parts.append(val)
        return " / ".join(parts)[:500] or "nothing yet"

    def process_one(self, sidecar: Path) -> dict | None:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        image = sidecar.with_suffix("").with_suffix(".jpg")
        if not image.exists():
            sidecar.unlink(missing_ok=True)
            return None
        entity_id = self._resolve_entity(meta)
        if not entity_id:
            sidecar.unlink(missing_ok=True)
            image.unlink(missing_ok=True)
            return None

        focus = meta.get("detail_focus", "overview")
        prompt = _PROMPTS.get(focus, _PROMPTS["overview"]).format(
            label=meta.get("label", "object"),
            known=self._known_so_far(entity_id),
        )
        description = _vlm_describe(image, prompt)
        stored = False
        if description and "nothing new" not in description.lower()[:40]:
            self.graph.ingest_enrichment_detail(
                entity_id, focus, description,
                captured_at=meta.get("captured_at", ""),
                level=int(meta.get("level", 1)),
            )
            if meta.get("label") == "person":
                self.graph.ingest_vlm_enrichment(
                    entity_id, description, meta.get("captured_at", "")
                )
            stored = True
        # Raw crop is consumed and deleted — no media retention.
        image.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        return {
            "entity_id": entity_id,
            "focus": focus,
            "stored": stored,
            "description": description[:160],
        }

    def run_forever(self, poll_s: float = 2.0) -> None:
        print(json.dumps({"type": "enricher_ready", "queue": str(self.queue_dir)}), flush=True)
        while True:
            for sidecar in sorted(self.queue_dir.glob("*.json")):
                try:
                    result = self.process_one(sidecar)
                except Exception as exc:  # keep the daemon alive; report and move on
                    print(json.dumps({"type": "enricher_error", "file": sidecar.name,
                                      "error": str(exc)[:200]}), flush=True)
                    sidecar.rename(sidecar.with_suffix(".json.failed"))
                    continue
                if result:
                    print(json.dumps({"type": "enrichment_stored", **result}), flush=True)
            time.sleep(poll_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/trace_hub.sqlite3")
    parser.add_argument("--queue", default="/tmp/trace_enrich")
    parser.add_argument("--once", action="store_true", help="process queue once and exit")
    args = parser.parse_args()

    db = Path(args.db)
    codec = EncryptedTextCodec.from_env_or_file(db.parent)
    graph = RelationalMemoryGraph(db, codec)
    queue_dir = Path(args.queue)
    queue_dir.mkdir(parents=True, exist_ok=True)
    enricher = Enricher(graph, queue_dir)

    if args.once:
        for sidecar in sorted(queue_dir.glob("*.json")):
            result = enricher.process_one(sidecar)
            if result:
                print(json.dumps({"type": "enrichment_stored", **result}), flush=True)
        return 0

    enricher.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
