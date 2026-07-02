#!/usr/bin/env python
"""TRACE prototype — the end-to-end LOCAL product path in one CLI.

    build:  frames -> OBSERVER (cheap CV triage) -> crop-zoom helpers (gemma-vision) ->
            store -> binder.  Raw frames are read in memory; only derived text persists.
    ask:    store + question -> local-Gemma reasoner -> answer + cited evidence + honest
            confidence (refuses what it never saw).

Everything runs locally: gemma on ollama is the only model. No frontier, no raw media kept.

    .venv/bin/python scripts/trace_prototype.py build <frames_dir> <store> [--observer] [--max-instances 8]
    .venv/bin/python scripts/trace_prototype.py ask <store> "what is in my room?" [--model gemma3:12b-it-qat]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("TRACE_EMBED_DEVICE", "cpu")  # keep the GPU for gemma

from trace_memory.store import TraceMemoryStore  # noqa: E402
from trace_memory.store.sleep import SleepConsolidator  # noqa: E402
from trace_memory.brain import TraceMemoryAgent  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent


def cmd_build(args: argparse.Namespace) -> int:
    # Perceive (observer-gated crop-zoom) by delegating to the ingest tool, then bind locally.
    ingest = [
        sys.executable, str(_ROOT / "scripts" / "crop_zoom_ingest.py"),
        "--frames", args.frames, "--store", args.store,
        "--max-instances", str(args.max_instances),
    ]
    if args.observer:
        ingest.append("--observer")
    if args.scene:
        ingest.append("--scene")
    env = {**os.environ, "TRACE_EMBED_DEVICE": "cpu", "TOKENIZERS_PARALLELISM": "false"}
    rc = subprocess.call(ingest, cwd=str(_ROOT), env=env)
    if rc != 0:
        return rc

    store = TraceMemoryStore(args.store)
    summary = SleepConsolidator(store).consolidate()  # local-gemma cited authoring
    authored = store.node_count(node_types=("entity_memory", "group_memory"))
    print(f"[build] bound store: {authored} authored memories, {summary.link_count} links")
    store.close()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    store = TraceMemoryStore(args.store)
    agent = TraceMemoryAgent(
        store, reasoner="local-ollama", ollama_model=args.model,
        restrict_sources=("phone_camera",),
    )
    ans = agent.answer(args.question)
    print(f"\nQ: {args.question}")
    print(f"A: {ans.answer}")
    print(f"   [confidence={ans.confidence:.2f}  refused={ans.refused}  via={ans.retrieval_mode}]")
    if ans.evidence_chain:
        print("   evidence:")
        for row in ans.evidence_chain[:4]:
            print(f"     - ({row.get('type')}) {str(row.get('text'))[:90]}")
    store.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("frames")
    b.add_argument("store")
    b.add_argument("--observer", action="store_true")
    b.add_argument("--scene", action="store_true")
    b.add_argument("--max-instances", type=int, default=8)
    b.set_defaults(func=cmd_build)

    a = sub.add_parser("ask")
    a.add_argument("store")
    a.add_argument("question")
    a.add_argument("--model", default="gemma3:12b-it-qat")
    a.set_defaults(func=cmd_ask)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
