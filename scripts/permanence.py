#!/usr/bin/env python3
"""Multi-object permanence — CLI over the library in trace_memory.store.permanence.

Collapse cross-frame RE-observations of the same physical object into distinct instances,
WITHOUT coordinates or pose (both unreliable/absent in real captures) and WITHOUT pixels
(product deletes frames; helpers run on-device and emit text). The only reliable signal in
the live stream is the helper text: label + described attributes (colour/material/kind) +
temporal order.

"is the object in frame 4 the same as the one in frame 25, or new?" — answered on text:
  same label + compatible attributes (same colour/material family) seen across frames -> ONE
  object re-observed (merge); same label but incompatible attributes -> DIFFERENT objects.
A local LLM (gemma) makes the merge/split call; a deterministic attribute-signature clusterer
is the offline fallback. The VLM's own per-frame count ("5 jar") is a FLOOR that rescues
identical-looking multiples that clustering cannot separate.

    .venv/bin/python scripts/permanence.py --store data/trace_store.sqlite3 \
        --subject "water bottle" --source phone_camera
    .venv/bin/python scripts/permanence.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trace_memory.store.permanence import count_instances  # noqa: E402


def _self_test() -> int:
    """Deterministic-path test: 7 reads of 2 physical mugs (colour drift) -> 2."""
    from trace_memory.store import TraceMemoryStore
    import tempfile, os
    db = os.path.join(tempfile.mkdtemp(), "perm_test.sqlite3")
    store = TraceMemoryStore(db)
    reads = [
        "OBJECT | coffee mug | teal ceramic mug | workbench | likely",
        "OBJECT | coffee mug | green cup | bench | likely",
        "OBJECT | coffee mug | cyan tumbler | tools | likely",
        "OBJECT | coffee mug | teal mug | left of keyboard | likely",
        "OBJECT | coffee mug | white mug | windowsill | likely",
        "OBJECT | coffee mug | pale cup | window | likely",
        "OBJECT | coffee mug | cream mug | across room | likely",
    ]
    for i, r in enumerate(reads):
        store.write_observation(text=r, t_ms=1000 + i * 200, source="phone_camera",
                                provenance={}, metadata={"section_kind": "physical_object"})
    res = count_instances(store, "coffee mug", sources=("phone_camera",), use_llm=False)
    store.close()
    ok = res.count == 2
    print(f"[self-test] deterministic count of coffee mugs = {res.count} (expect 2) "
          f"-> {'PASS' if ok else 'FAIL'}")
    for inst in res.instances:
        print(f"   instance: {inst['canonical']!r}  ({inst['n_frames']} frames)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store")
    ap.add_argument("--subject")
    ap.add_argument("--source", default="")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if not args.store or not args.subject:
        ap.error("--store and --subject required (or --self-test)")
    from trace_memory.store import TraceMemoryStore
    sources = tuple(s.strip() for s in args.source.split(",") if s.strip()) or None
    store = TraceMemoryStore(args.store)
    try:
        res = count_instances(store, args.subject, sources=sources, model=args.model,
                              host=args.host, use_llm=not args.no_llm)
    finally:
        store.close()
    print(json.dumps({
        "subject": res.subject, "count": res.count, "method": res.method,
        "n_reads": res.n_reads, "frame_count_floor": res.floor,
        "floor_evidence": res.floor_evidence,
        "instances": [{"canonical": i["canonical"], "n_frames": i["n_frames"]}
                      for i in res.instances],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
