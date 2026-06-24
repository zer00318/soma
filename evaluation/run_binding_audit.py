#!/usr/bin/env python3
"""Local-LLM grind job: a MEASURED binding-precision number for the WS2 binder.

The founder is (rightly) skeptical of estimated progress %s. This replaces an estimate
with a measurement: of the entities the binder marks CONFIDENT, what fraction are actually
coherent real things (a sign/label/phrase) vs garbled OCR noise the binder over-trusted?
That is binding PRECISION — the metric that matters for the moat (a wrong confident bind is
a confident lie). The judge is the ON-DEVICE LLM (gemma), so this burns local compute, not
Claude tokens — exactly the 24/7-local-LLM directive.

Self-contained + CHECKPOINTED (resumable): writes ops/cockpit/binding_audit.json after every
judged entity, and narrates to the cockpit flight recorder. Bounded (audits each clip once,
then exits cleanly) so it never thrashes the box. Relaunch to re-grind.

Run (LOCAL — reaches ollama):
  PYTHONUNBUFFERED=1 caffeinate -is .venv/bin/python evaluation/run_binding_audit.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import inject_bind  # noqa: E402

OUT = os.path.join(ROOT, "ops", "cockpit", "binding_audit.json")
CLIPS = [
    ("day", os.path.join(ROOT, "data/live_replay/day_in_life_20260618_live44/memory")),
    ("walk", os.path.join(ROOT, "data/live_replay/walk_outside_20260614_live44/memory")),
]
MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"


def clog(kind, text):
    try:
        import clog as _c  # scripts/clog.py
        _c.log(kind, text)
    except Exception:
        pass


def ollama(prompt, timeout=60):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.0}}).encode()
    req = urllib.request.Request(HOST + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()).get("response", "")


JUDGE = (
    "A wearable capture system read text across {support} video frames and grouped it into "
    "ONE entity with the consensus value:\n  \"{value}\"\n"
    "Is this a COHERENT real thing a person could have read (a sign, label, screen text, a "
    "phrase, a time, a place), or is it GARBLED OCR NOISE that should not be trusted?\n"
    "Answer with exactly one word: COHERENT or NOISE."
)


def judge(entity):
    try:
        out = ollama(JUDGE.format(support=entity["support"], value=entity["value"][:120]))
    except Exception as e:
        return None, f"err:{e!r}"[:60]
    verdict = "COHERENT" if "COHERENT" in out.upper() else ("NOISE" if "NOISE" in out.upper() else None)
    return verdict, out.strip()[:80]


def save(state):
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, OUT)


def main():
    state = {"status": "running", "started": int(time.time()), "model": MODEL,
             "clips": {}, "overall": {}}
    if os.path.exists(OUT):
        try:
            state = json.load(open(OUT))
            state["status"] = "running"
        except Exception:
            pass
    clog("run", "Binding-precision audit STARTED on local gemma (measuring real precision of the binder).")
    tot_c = tot_n = 0
    for clip, memdir in CLIPS:
        res = inject_bind.bind_memory(memdir)
        confident = [e for e in res["entities"] if not e["speculative"]]
        done = state["clips"].get(clip, {}).get("judged", [])
        done_vals = {d["value"] for d in done}
        for e in confident:
            if e["value"] in done_vals:
                continue
            v, raw = judge(e)
            done.append({"value": e["value"], "support": e["support"],
                         "binding_confidence": e["binding_confidence"], "verdict": v})
            coh = sum(1 for d in done if d["verdict"] == "COHERENT")
            noise = sum(1 for d in done if d["verdict"] == "NOISE")
            prec = round(coh / max(1, coh + noise) * 100, 1)
            state["clips"][clip] = {"confident_total": len(confident), "judged": done,
                                    "coherent": coh, "noise": noise, "precision_pct": prec}
            save(state)
        c = state["clips"][clip]
        clog("eval", f"Binding audit · {clip}: precision {c['precision_pct']}% "
                     f"({c['coherent']} coherent / {c['noise']} noise of {c['confident_total']} confident binds).")
        tot_c += state["clips"][clip]["coherent"]
        tot_n += state["clips"][clip]["noise"]
    overall = round(tot_c / max(1, tot_c + tot_n) * 100, 1)
    state["overall"] = {"coherent": tot_c, "noise": tot_n, "precision_pct": overall}
    state["status"] = "done"
    state["finished"] = int(time.time())
    save(state)
    clog("done", f"Binding-precision audit DONE: {overall}% of confident binds are coherent "
                 f"({tot_c} coherent / {tot_n} noise). MEASURED, on local gemma.")
    print("DONE overall precision", overall, "%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
