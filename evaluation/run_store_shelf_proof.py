#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.annotate_live import load_annotations, score_annotations, summarize
from trace_memory.store import TraceMemoryStore, ingest_validated_shelf

DEFAULT_CAPTURE_DIR = "data/phone_captures/_validated_shelf_20260627"
DEFAULT_ANNOTATIONS = "data/phone_captures/live/ground_truth.json"
DEFAULT_STORE = "data/phone_captures/_validated_shelf_20260627/trace_store.sqlite3"
DEFAULT_STATUS = "ops/cockpit/store_ingest.json"


def _proof_queries() -> tuple[str, ...]:
    return (
        "nutella jar",
        "ring gemstone",
        "pesto",
        "macbook",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", default=DEFAULT_CAPTURE_DIR)
    parser.add_argument("--annotations", default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--store", default=DEFAULT_STORE)
    parser.add_argument("--status-out", default=DEFAULT_STATUS)
    parser.add_argument("--reasoner", choices=("heuristic", "local-ollama"), default="heuristic")
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()

    store_path = Path(args.store)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if store_path.exists():
        store_path.unlink()

    store = TraceMemoryStore(store_path)
    try:
        ingest = ingest_validated_shelf(store, args.capture_dir)
        query_checks = []
        for query in _proof_queries():
            search = store.search(query, k=3)
            query_checks.append(
                {
                    "query": query,
                    "retrieval_mode": search.retrieval_mode,
                    "degraded": search.degraded,
                    "hit_count": len(search.hits),
                    "top_hits": [hit.node.text[:140] for hit in search.hits[:2]],
                }
            )
        annotations = load_annotations(Path(args.annotations))
        results = score_annotations(
            annotations,
            store,
            reasoner=args.reasoner,
            model=args.model,
            host=args.host,
            repeats=max(1, args.repeats),
        )
        summary = summarize(results)
        payload = {
            "state": "complete",
            "note": (
                f"shelf store ready: {summary['answered']}/{summary['total']} answered, "
                f"{summary['confident_wrong']} confident-wrong"
            ),
            "capture_dir": args.capture_dir,
            "store": str(store_path),
            "retrieval_mode": store.retrieval_mode,
            "observation_count": store.node_count(node_types=("observation",)),
            "entity_count": store.node_count(node_types=("entity",)),
            "abstraction_count": len(store.get_abstractions()),
            "link_count": store.link_count(),
            "frame_node_count": len(ingest.frame_nodes),
            "entity_node_count": len(ingest.entity_nodes),
            "graph_summary": ingest.graph_summary,
            "query_checks": query_checks,
            "answered_rate": summary["answered_rate"],
            "correct_rate": summary["correct_rate"],
            "confident_wrong_rate": summary["confident_wrong_rate"],
            "confident_wrong": summary["confident_wrong"],
        }
    finally:
        store.close()

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    status_path = Path(args.status_out)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
