#!/usr/bin/env python3
"""Founder's test: for every wrong/miss, did the brain RECEIVE the gold fact?

Three-way split per failing question:
  BRAIN      gold cue is IN the dossier the model saw  -> saw it, still failed
  RETRIEVAL  gold cue is in raw memory but NOT in the dossier -> captured, not surfaced
  CAPTURE    gold cue is absent from ALL captured channels -> genuinely missing
No clip-specific logic; cues come straight from the gold's `accept` list.
"""
import json, os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import ask_home as A

CLIPS = {
    "cold": dict(
        mem="data/walks/day_in_life_20260618/memory/world_memory.json",
        gold="evaluation/ras/day_in_life_20260618.gold.json",
        ckpt="ops/cockpit/rescore_checkpoints/cold.jsonl"),
    "walk": dict(
        mem="data/walks/walk_outside_20260614/memory/world_memory.json",
        gold="evaluation/ras/walk_outside_20260614.gold.json",
        ckpt="ops/cockpit/rescore_checkpoints/walk.jsonl"),
}

def norm(s): return re.sub(r"\s+", " ", str(s).lower())
STOP = {"yes","no","the","a","an","not","two","three","one","red","blue","green",
        "white","black","gray","grey","open","closed","you","i","it","he","she"}

def distinctive(cue):
    """tokens worth trusting as a fingerprint: len>=4 and not a bare colour/yes-no."""
    return [w for w in re.split(r"[^a-z0-9]+", norm(cue))
            if len(w) >= 4 and w not in STOP]

def present(cues, text):
    """Return (hit_str, confidence). HIGH = a distinctive multi/long token matched on
    a word boundary; LOW = only generic cues (no/yes/colour) matched -> not trusted."""
    t = norm(text)
    low = None
    for c in cues:
        toks = distinctive(c)
        if toks and all(re.search(r"\b" + re.escape(w) + r"\b", t) for w in toks):
            return (c, "HIGH")
        cc = norm(c)
        if cc and re.search(r"\b" + re.escape(cc) + r"\b", t):
            low = cc
    return (low, "LOW") if low else (None, None)

def raw_blob(mem_path):
    base = os.path.dirname(os.path.abspath(mem_path))
    chunks = []
    for fn in os.listdir(base):
        if fn.endswith((".json", ".ndjson", ".txt")) and "semidx" not in fn:
            try:
                chunks.append(open(os.path.join(base, fn), errors="ignore").read())
            except Exception:
                pass
    return "\n".join(chunks)

for clip, cfg in CLIPS.items():
    gold = json.load(open(cfg["gold"]))["items"]
    ck = {}
    for l in open(cfg["ckpt"]):
        if l.strip():
            r = json.loads(l); ck[str(r["i"])] = r
    mems = A._resolve_memories(cfg["mem"])
    blob = raw_blob(cfg["mem"])
    tally = {"BRAIN": 0, "RETRIEVAL": 0, "CAPTURE": 0, "REFUSE_OK": 0}
    print(f"\n================  {clip.upper()}  ================")
    for qi, g in gold.items():
        r = ck.get(str(qi))
        if not r or r.get("verdict") == "correct":
            continue
        cues = g.get("accept") or []
        ch = g.get("channel", "?")
        dossier = ""
        try:
            channels = A.gather_evidence(g["q"], cfg["mem"], mems)
            d = A.build_evidence_dossier(g["q"], channels)
            dossier = d[0] if isinstance(d, (list, tuple)) else str(d)
        except Exception as e:
            dossier = f"<dossier error: {e}>"
        doss_hit, doss_conf = present(cues, dossier)
        raw_hit, raw_conf = present(cues, blob)
        if not cues:
            cls = "REFUSE_OK"
        elif doss_conf == "HIGH":
            cls = "BRAIN"
        elif raw_conf == "HIGH":
            cls = "RETRIEVAL"
        elif doss_conf == "LOW" or raw_conf == "LOW":
            cls = "LOWCONF"
        else:
            cls = "CAPTURE"
        tally[cls] = tally.get(cls, 0) + 1
        hit = doss_hit or raw_hit or "-"
        loc = "dossier" if doss_conf else ("raw-only" if raw_conf else "-")
        print(f"  Q{qi:<2} [{r['verdict']:<7}] {cls:<9} {loc:<8} ch={ch:<20} cue={str(hit)[:26]:<26} | {g['q'][:42]}")
    print(f"  --- {clip} tally: {tally}")
