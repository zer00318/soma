#!/usr/bin/env python3
"""SOMA overnight 'sleep' job — all LOCAL models, checkpointed, no Claude needed.

The founder's sleep idea, automated: while he sleeps, the local models (gemma for
reasoning, the assembler for answering) work the walk and leave a morning report.
Three phases, each checkpointed so a kill/limit just resumes on re-run:

  A. GAP DISCOVERY (evolve-by-question, automated) — gemma invents a large, diverse
     question battery about a walk like this; the assembler answers each; we classify
     answered / weak / GAP(refused). The gaps, grouped by category, ARE the ranked
     list of subsystems to build next.
  B. OBJECTIVE RE-SCORE — the resumable run_live against the frozen gold key.
  C. MORNING REPORT — ops/overnight_report.md: the number, the top gaps, regressions.

Run:  nohup python3 scripts/overnight_sleep.py > /tmp/overnight_sleep.log 2>&1 &
Re-run the same command any time to resume (skips finished work).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import ask_home  # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = "gemma3:12b-it-qat"
MEM = str(ROOT / "data/walks/walk_outside_20260614/memory/world_memory.json")
WORK = ROOT / "data/walks/walk_outside_20260614/overnight"
WORK.mkdir(exist_ok=True)
QFILE = WORK / "selfplay_questions.json"
CKPT = WORK / "selfplay_answers.ndjson"
REPORT = ROOT / "ops/overnight_report.md"
N_QUESTIONS = 60


def _gen(prompt, timeout=240, model=MODEL):
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.4}}).encode()
    req = urllib.request.Request(OLLAMA, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace")).get("response", "").strip()


def _log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


# --------------------------------------------------------------------------- #
# Phase A: self-play gap discovery
# --------------------------------------------------------------------------- #
QGEN = (
    "A person took a short walk that passed through a train/subway station with science\n"
    "posters (scientists, a molecule, an X-ray), used a laptop on a cart, carried a bag,\n"
    "and there were signs and a door. Generate %d DIVERSE, SPECIFIC questions they might\n"
    "ask later about that day. Spread them across these categories and PREFIX each line\n"
    "with the category and a colon:\n"
    "  text:  (signs/posters/screens — what did they say)\n"
    "  objects:  (what things were there)\n"
    "  attributes:  (colour / open-closed / on-off / material of a thing)\n"
    "  people:  (anyone present, what they wore/held)\n"
    "  places:  (where am I / layout / which place)\n"
    "  events:  (what happened, in what order, did I do X)\n"
    "  audio:  (sounds, speech, a cry, an alarm)\n"
    "  screen:  (what was on the laptop/phone screen)\n"
    "  temporal:  (how long did I spend on X)\n"
    "  spatial:  (where was X relative to me / which side)\n"
    "One question per line, no numbering. Make them concrete (ask about specific things)."
    % N_QUESTIONS)


def gen_questions():
    if QFILE.exists():
        return json.loads(QFILE.read_text())
    _log("Phase A: generating self-play questions (gemma)...")
    raw = _gen(QGEN)
    qs = []
    for line in raw.splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()
        if ":" in line and len(line) > 8:
            cat, _, q = line.partition(":")
            cat = cat.strip().lower()
            q = q.strip()
            if q and cat in ("text", "objects", "attributes", "people", "places",
                             "events", "audio", "screen", "temporal", "spatial"):
                qs.append({"category": cat, "question": q})
    QFILE.write_text(json.dumps(qs, indent=2, ensure_ascii=False))
    _log("  generated %d questions" % len(qs))
    return qs


CONF = (
    "An automatic memory answered a question. Reply with ONE word: CONFIDENT if the answer\n"
    "gives a concrete, specific fact; WEAK if it is vague, hedged, or partial; REFUSED if it\n"
    "says it doesn't know / didn't capture it.\n\nQuestion: %s\nAnswer: %s\nWord:")


def run_gap_discovery(qs):
    done = set()
    if CKPT.exists():
        for line in CKPT.read_text().splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["question"])
                except Exception:
                    pass
    _log("Phase A: answering %d questions (%d already done)..." % (len(qs), len(done)))
    for q in qs:
        if q["question"] in done:
            continue
        try:
            ans = ask_home.ask(q["question"], MEM).get("answer", "")
        except Exception as exc:
            ans = "[engine error: %s]" % exc
        if ask_home._is_refusal(ans):
            status = "gap"
        else:
            try:
                v = _gen(CONF % (q["question"], ans), timeout=120).strip().upper()
            except Exception:
                v = "WEAK"
            status = "gap" if v.startswith("REFUS") else ("weak" if v.startswith("WEAK") else "answered")
        row = {"category": q["category"], "question": q["question"], "answer": ans, "status": status}
        with CKPT.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _log("Phase A done.")


def load_gap_rows():
    rows = []
    if CKPT.exists():
        for line in CKPT.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


# --------------------------------------------------------------------------- #
# Phase B: objective re-score (resumable run_live)
# --------------------------------------------------------------------------- #
def run_rescore():
    _log("Phase B: objective gold re-score (resumable run_live)...")
    ck = "/tmp/walk_live_overnight.jsonl"
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "evaluation/run_live.py"),
             "--questions", str(ROOT / "evaluation/ras/walk_outside_20260614.txt"),
             "--gold", str(ROOT / "evaluation/ras/walk_outside_20260614.gold.json"),
             "--memory", MEM, "--checkpoint", ck,
             "--status", str(ROOT / "ops/cockpit/eval_live.json")],
            timeout=3600, cwd=str(ROOT))
    except Exception as exc:
        _log("  re-score note: %s" % exc)
    rows = []
    if Path(ck).exists():
        for line in Path(ck).read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


# --------------------------------------------------------------------------- #
# Phase C: morning report
# --------------------------------------------------------------------------- #
def write_report(gap_rows, score_rows):
    by_cat = defaultdict(lambda: Counter())
    for r in gap_rows:
        by_cat[r["category"]][r["status"]] += 1
    gap_cats = sorted(by_cat.items(),
                      key=lambda kv: -(kv[1]["gap"] + 0.5 * kv[1]["weak"]))

    hard = [r for r in score_rows if not r.get("pending")]
    hc = sum(1 for r in hard if r["verdict"] == "correct")
    hw = sum(1 for r in hard if r["verdict"] == "wrong")
    ras = round((hc - hw) / max(len(hard), 1) * 100, 1)

    lines = ["# SOMA overnight report", "",
             "_Generated by the local-model sleep job. All work done on-device._", ""]
    lines.append("## Objective number (frozen gold key)")
    if score_rows:
        lines.append("- hard RAS = **%+.1f**  (correct %d / wrong %d / scored %d of 25)"
                     % (ras, hc, hw, len(score_rows)))
        wrongs = [r for r in score_rows if r["verdict"] == "wrong"]
        if wrongs:
            lines.append("- still wrong:")
            for r in wrongs:
                lines.append("  - Q%s: %s" % (r.get("i"), (r.get("answer") or "")[:90]))
    else:
        lines.append("- (re-score did not complete; re-run overnight_sleep.py to resume)")
    lines += ["", "## Gap discovery — what to build next (ranked by where it can't answer)"]
    total = len(gap_rows)
    g = sum(1 for r in gap_rows if r["status"] == "gap")
    w = sum(1 for r in gap_rows if r["status"] == "weak")
    lines.append("- self-play questions answered: %d  |  gaps: %d  weak: %d  solid: %d"
                 % (total, g, w, total - g - w))
    for cat, cnt in gap_cats:
        if cnt["gap"] or cnt["weak"]:
            lines.append("- **%s** — %d gap / %d weak / %d solid"
                         % (cat, cnt["gap"], cnt["weak"], cnt["answered"]))
    lines += ["", "### Sample gaps (the questions it could not answer)"]
    for r in [x for x in gap_rows if x["status"] == "gap"][:12]:
        lines.append("- [%s] %s" % (r["category"], r["question"]))
    REPORT.write_text("\n".join(lines))
    _log("Wrote %s" % REPORT)


def main():
    _log("=== overnight sleep job start ===")
    qs = gen_questions()
    run_gap_discovery(qs)
    gap_rows = load_gap_rows()
    score_rows = run_rescore()
    write_report(gap_rows, score_rows)
    # Refresh the durable scoreboard + run the INDEPENDENT objective critic on the
    # fresh number, so every nightly pass ends with an unbiased verdict the lead did
    # not author (ops/cockpit/critic.json). One-way: it judges, it is not steered.
    try:
        ck = ROOT / "ops/cockpit/scoreboard.jsonl"
        live = ROOT / "evaluation/run_live_overnight.jsonl"  # leftover safety; prefer the rescore ckpt
        src = Path("/tmp/walk_live_overnight.jsonl")
        if src.exists():
            ck.write_text(src.read_text())
            subprocess.run([
                sys.executable, str(ROOT / "scripts/objective_critic.py"),
                "--clip", "walk", "--scoreboard", str(src),
            ], timeout=600, cwd=str(ROOT), check=True)
        else:
            _log("  critic skipped: fresh overnight WALK checkpoint missing")
    except Exception as exc:
        _log("  critic note: %s" % exc)
    _log("=== overnight sleep job done ===")


if __name__ == "__main__":
    main()
