#!/usr/bin/env python3
"""Gate diagnostic: for chosen question ids, show the assembler DRAFT, the grounding-gate
verdict, and whether the gold accept-terms appear in (a) the draft and (b) the dossier.

This tells us mechanically whether the grounding gate is OVER-firing (killing a draft that
actually contained the gold) vs doing its job (killing an unsupported guess). No file writes.

Usage: python3 scripts/diag_gate.py 2 6 10 12 15 19   (defaults to a standard set)
"""
from __future__ import annotations
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "evaluation"))
import ask_home as H  # noqa
from run_ras import _load_questions  # noqa

MEM = os.path.join(ROOT, "data/walks/walk_outside_20260614/memory/world_memory.json")
QF = os.path.join(ROOT, "evaluation/ras/walk_outside_20260614.txt")
GF = os.path.join(ROOT, "evaluation/ras/walk_outside_20260614.gold.json")
MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"

qids = [int(x) for x in sys.argv[1:]] or [2, 6, 10, 12, 15, 19]
questions = _load_questions(__import__("pathlib").Path(QF))
gold = json.load(open(GF))["items"]
mems = H._resolve_memories(MEM)

def hit(terms, text):
    t = (text or "").lower()
    return [w for w in (terms or []) if w.lower() in t]

out = []
for i in qids:
    q = questions[i - 1]["question"]
    g = gold.get(str(i), {})
    accept = g.get("accept", [])
    channels = H.gather_evidence(q, MEM, mems)
    dossier, cited = H.build_evidence_dossier(q, channels)
    draft = H.think_and_answer(q, dossier, MODEL, HOST, 240)
    supported = H.verify_grounded(q, dossier, draft, MODEL, HOST, 240)
    rec = {
        "i": i, "q": q,
        "draft": draft,
        "gate": "SUPPORTED" if supported else "UNSUPPORTED->demoted",
        "draft_is_refusal": H._is_refusal(draft),
        "accept_in_draft": hit(accept, draft),
        "accept_in_dossier": hit(accept, dossier),
        "dossier_len": len(dossier),
    }
    out.append(rec)
    print("=" * 70)
    print("Q%d: %s" % (i, q))
    print("DRAFT:", (draft or "")[:400])
    print("GATE:", rec["gate"], "| accept_in_draft:", rec["accept_in_draft"],
          "| accept_in_dossier:", rec["accept_in_dossier"])
    sys.stdout.flush()

json.dump(out, open("/tmp/diag_gate.json", "w"), ensure_ascii=False, indent=2)
print("\nwrote /tmp/diag_gate.json")
