#!/usr/bin/env python3
"""Cross-frame OCR consensus recall — the narrow product's real test.

The product is "a memory for everything you READ". The camera sees a continuous
stream; the memory accumulates every line Apple-Vision OCR extracts. The eval's
per-frame questions reference scene facts (a plaque's dates, a sign's name) that
the live camera read across MANY adjacent frames — often truncated/garbled in any
single frame but verbatim in neighbours. So we answer each question from the OCR
read in a TEMPORAL WINDOW around its frame, where line FREQUENCY is the confidence
signal: text that repeats across the zoom-sweep is trusted; one-off garble is
fail-safe-dropped. Answers come OCR-first (no VLM colour/object channel — that
channel fabricates). If no repeated line supports an answer, we refuse.

All inference local (ollama). Run from repo root:
  .venv/bin/python evaluation/ocr_recall.py [--half 8] [--minrep 2]
"""
import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evaluation.vision_ocr import ocr_image

FRAMES = "data/walks/walk_outside_20260614/work/run_frames"
MEMO = "/tmp/ocr_memory.json"            # cache: {frame_name: [ocr lines]}
MODEL = "gemma3:12b-it-qat"           # overridden by --model
HOST = "http://127.0.0.1:11434"

# Keyboard rows and lone glyphs the OCR grabs off the laptop body — pure noise that
# must never become an answer. A line is noise if most of its tokens are <=2 chars.
_KEYS = {"command", "option", "control", "fn", "esc", "shift", "ctrl", "tab", "caps"}

# The 15 text-recall questions (read off signs / screens / plaques) — the subset
# the pivot narrowed to. Everything else (colour/scene/count) is descoped.
TEXT_IDS = {2, 4, 5, 7, 10, 22, 24, 25, 26, 33, 36, 40, 42, 43, 46}

ANSWER = (
    "You are a person's memory of text they READ a moment ago. The original image is gone; you "
    "have ONLY these lines your eyes read, top-to-bottom, as Apple-Vision OCR (may be slightly "
    "garbled). Lines that are physically adjacent belong together (a name and the dates under it).\n"
    "--- WHAT YOU READ ---\n{ctx}\n---\n"
    "Answer with ONLY the specific thing asked — the name, the year/date range, the street — "
    "copied verbatim from the lines above, with NO surrounding words, labels, or punctuation. "
    "If that specific thing is not present in the lines, output EXACTLY: NOT IN MEMORY. Do not "
    "guess, infer, or use outside knowledge.\nQuestion: {q}"
)
JUDGE = (
    'A person asked about a photo. HUMAN ground truth: "{gold}". System answered: "{ans}". '
    'If the ground truth says a thing is ABSENT and the system asserts it exists -> WRONG; if the '
    'system also says absent -> CORRECT. Else if the system answer is factually consistent with the '
    'ground truth (same name/number/word, minor formatting aside) -> CORRECT, else WRONG. '
    'Output ONE word: CORRECT or WRONG.'
)


def is_noise(line):
    toks = line.split()
    if not toks:
        return True
    if all(t.lower().strip(",.|") in _KEYS for t in toks):
        return True
    short = sum(1 for t in toks if len(t.strip(",.|€#")) <= 2)
    return len(toks) >= 3 and short / len(toks) > 0.6


def oll(prompt, images=None, model=None):
    p = {"model": model or MODEL, "prompt": prompt, "stream": False,
         "options": {"temperature": 0}}
    if images:
        p["images"] = images
    data = json.dumps(p).encode()
    last = None
    for attempt in range(4):  # 27b occasionally 500s under memory pressure; retry
        try:
            req = urllib.request.Request(HOST + "/api/generate", data=data,
                                         headers={"content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read()).get("response", "").strip()
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def load_memory():
    if Path(MEMO).exists():
        return json.load(open(MEMO))
    mem = {}
    for p in sorted(Path(FRAMES).glob("frame_*.jpg")):
        mem[p.name] = ocr_image(str(p))
    json.dump(mem, open(MEMO, "w"), ensure_ascii=False)
    return mem


def secs(frame_name):
    m = re.search(r"_(\d+\.\d+)s", frame_name)
    return float(m.group(1)) if m else 0.0


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def window_frames(memory, center, half):
    """Distinct, non-empty per-frame OCR readings within +-half seconds of center.

    Each frame keeps its own top-to-bottom line order (spatial adjacency is what
    binds a name to the dates under it). Frames with identical OCR are deduped, and
    the nearest-to-center frame is preferred so ties break toward the asked moment.
    """
    cands = []
    for fname, ls in memory.items():
        ls = [l for l in ls if l.strip() and not is_noise(l)]
        if not ls or abs(secs(fname) - center) > half:
            continue
        cands.append((abs(secs(fname) - center), fname, ls))
    cands.sort()  # nearest first
    seen, frames = set(), []
    for dist, fname, ls in cands:
        key = tuple(_norm(l) for l in ls)
        if key in seen:
            continue
        seen.add(key)
        frames.append((dist, ls))
    return frames


def vote_answer(memory, center, half, question, minrep, model=None, max_frames=20):
    """Society-of-frames: answer the question from EACH frame's local OCR, then vote.

    The frame that read the sign cleanly yields the full string; truncated frames
    refuse or yield fragments; the majority non-refusal answer wins (refusals never
    vote). Requires >= minrep frames to agree, so a one-off misread can't win — that
    is the self-calibrating honesty: consensus or silence.
    """
    frames = window_frames(memory, center, half)[:max_frames]
    tally = collections.Counter()
    reps, dist0 = {}, {}
    for dist, ls in frames:
        ctx = "\n".join(ls)[:1400]  # cap dense screen dumps so 27b doesn't OOM/500
        ans = oll(ANSWER.format(ctx=ctx, q=question), model=model)
        if "NOT IN MEMORY" in ans.upper():
            continue
        # The answerer sometimes glues an adjacent OCR fragment onto the real value
        # ("Max-Planck-Campus\nROB\nmargen"). Keep the substantive line (the longest),
        # so a junk prefix/suffix can't poison the spoken answer or the judge.
        ans = max(ans.splitlines(), key=len).strip()
        k = _norm(ans)
        if not k:
            continue
        tally[k] += 1
        if k not in reps or dist < dist0[k]:
            reps[k], dist0[k] = ans, dist
    if not tally:
        return "NOT IN MEMORY", {}
    # Substring clustering: a truncated read ("1881") is the SAME fact as the full
    # read ("1881 - 1945"), not a competitor — fold the shorter into the longer and
    # sum their votes. This makes the camera's many partial glimpses reinforce the
    # one complete glimpse instead of splitting the vote.
    merged = collections.Counter()
    canon_rep = {}
    for k in sorted(tally, key=len, reverse=True):
        host = next((c for c in merged if k in c), None)
        if host is None:
            merged[k] = tally[k]
            canon_rep[k] = reps[k]
        else:
            merged[host] += tally[k]
            # keep the most COMPLETE reading as the spoken answer, never the truncated one
            if len(reps[k]) > len(canon_rep[host]):
                canon_rep[host] = reps[k]
    top = max(merged.items(), key=lambda kv: (kv[1], len(kv[0])))
    # A date-shaped read (NNNN - NNNN) is structurally not a misread, so one clean
    # sighting is enough; everything else needs >= minrep agreeing frames.
    is_date = bool(re.fullmatch(r"\d{4}\s*-?\s*\d{0,4}", top[0].strip()))
    if top[1] < minrep and not (is_date and top[1] >= 1):
        return "NOT IN MEMORY", dict(merged)
    return canon_rep[top[0]], dict(merged)


def judge(gold, ans):
    if "NOT IN MEMORY" in ans.upper():
        return "REFUSED"
    v = oll(JUDGE.format(gold=gold, ans=ans)).upper()
    return "CORRECT" if "CORRECT" in v else "WRONG"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", type=float, default=5.0, help="window half-width seconds")
    ap.add_argument("--minrep", type=int, default=3, help="min frames a line must repeat in")
    ap.add_argument("--all", action="store_true", help="score all 48, not just text subset")
    ap.add_argument("--model", default="gemma3:27b-it-qat",
                    help="ollama model for the per-frame answerer (recall is on-demand, can afford 27b)")
    args = ap.parse_args()

    memory = load_memory()
    rows = json.load(open("evaluation/ras/posthoc_ablation_n16.json"))["rows"]
    gold = {g["id"]: g["gold"] for g in json.load(open("/tmp/founder_gold.json"))}

    out = []
    for i, r in enumerate(rows):
        if i not in gold:
            continue
        if not args.all and i not in TEXT_IDS:
            continue
        ans, tally = vote_answer(memory, secs(r["frame"]), args.half, r["question"],
                                 args.minrep, model=args.model)
        v = judge(gold[i], ans)
        out.append({"id": i, "v": v, "gold": gold[i], "ans": ans, "q": r["question"], "tally": tally})
        print(f"{i:2} {v:7} | gold: {gold[i][:30]:30} | sys: {ans[:32]:32} | votes: {tally}", flush=True)

    c = collections.Counter(x["v"] for x in out)
    n = len(out)
    cor, wr = c["CORRECT"], c["WRONG"]
    ans_n = cor + wr
    label = "ALL 48" if args.all else "TEXT subset (15)"
    print(f"\n=== consensus recall, half={args.half}s minrep={args.minrep} — {label} ===")
    print("counts:", dict(c))
    print(f"correct: {cor}/{n} = {cor/n:.1%}   hallucination(wrong/answered): "
          f"{wr/ans_n if ans_n else 0:.1%}")
    print("TARGET: >=60% correct AND <10% hallucination")
    tag = "text" if not args.all else "all"
    json.dump({"half": args.half, "minrep": args.minrep, "summary": dict(c),
               "correct_frac": round(cor / n, 3),
               "halluc_frac": round(wr / ans_n, 3) if ans_n else 0, "rows": out},
              open(f"evaluation/ras/ocr_recall_{tag}_foundergold.json", "w"),
              indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
