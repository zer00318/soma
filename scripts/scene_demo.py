#!/usr/bin/env python3
"""One-shot scene demo: a high-res photo in, honest answers out.

Chains the whole new pipeline:
  detector (Grounding-DINO) -> per-instance crop -> strong VLM read
  -> scene graph (relations from geometry) -> LLM meta-reasoning.

    .venv/bin/python scripts/scene_demo.py <photo.jpg> \
        --ask "how many snacks" "what brand of ketchup" "is there a laptop"

Privacy: the image and crops are processed in memory; only the derived instance
text/boxes are kept. No raw media is persisted by this script.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import instance_perceive as ip
import instance_graph as ig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--max-instances", type=int, default=12)
    ap.add_argument("--ask", nargs="*", default=[
        "What objects are in the scene?",
        "What brands or products can you read?",
    ])
    args = ap.parse_args()

    print(f"perceiving {Path(args.image).name} (detector -> crops -> VLM)...")
    instances = ip.perceive(args.image, args.max_instances)
    graph = ig.build_graph(instances)
    print("\n" + ig.render_graph(graph))
    for q in args.ask:
        print(f"\nQ: {q}\n  A: {ig.answer(graph, q)}")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
