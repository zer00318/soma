#!/usr/bin/env python3
"""Falsifiable test: does the Vision-OCR + native-res capture move the honest number?

Re-derives the 16 walk frames with the PRODUCTION path now (VLM scene/objects +
Apple Vision OCR as the authoritative verbatim TEXT channel, full resolution),
re-answers the 48 questions strictly, and judges against the FOUNDER's human gold.
Refusals are detected deterministically (the model outputs exactly NOT IN MEMORY),
so the judge only grades real answers -> no more counting refusals as wrong.

All inference is local (ollama). Run from repo root: .venv/bin/python evaluation/ocr_rerun.py
"""
import base64
import collections
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evaluation.vision_ocr import ocr_image

FRAMES = "data/walks/walk_outside_20260614/work/run_frames"
MODEL = "gemma3:12b-it-qat"
HOST = "http://127.0.0.1:11434"

PERCEIVE = (
    "You are a person's first-person camera walking through the world. Report ONLY "
    "what is actually visible in THIS frame — never guess or carry over. Output exactly:\n"
    "SCENE: <one short sentence>\nOBJECTS: <comma-separated concrete things you actually see>\n"
    "TEXT: <any on-screen/sign text copied verbatim, or NONE>\n"
    "PEOPLE: <count and what they appear to be doing, or NONE>"
)
STRICT = (
    "You are Trace's memory. The original image was DISCARDED; you have ONLY this derived text:\n"
    "---\n{d}\n---\nAnswer by copying the exact relevant words from the text. If the text does not "
    "directly contain the answer, output EXACTLY: NOT IN MEMORY. Do not paraphrase, infer, or add "
    "anything. One short answer.\nQuestion: {q}"
)
JUDGE = (
    'A person asked about a photo. HUMAN ground truth: "{gold}". System answered: "{ans}". '
    'If the ground truth says a thing is ABSENT (e.g. "there is no X") and the system asserts it '
    'exists -> WRONG; if the system also says absent -> CORRECT. Else if the system answer is '
    'factually consistent with the ground truth -> CORRECT, otherwise WRONG. Output ONE word: CORRECT or WRONG.'
)


def oll(prompt, images=None):
    p = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if images:
        p["images"] = images
    req = urllib.request.Request(HOST + "/api/generate", data=json.dumps(p).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def merge_text(vlm, ocr_lines):
    ocr = " | ".join(s.strip() for s in ocr_lines if s.strip())
    line = f"TEXT: {ocr}" if ocr else "TEXT: NONE"
    out, rep = [], False
    for ln in vlm.splitlines():
        if ln.upper().startswith("TEXT:"):
            out.append(line); rep = True
        else:
            out.append(ln)
    if not rep:
        out.append(line)
    return "\n".join(out)


def judge(gold, ans):
    if "NOT IN MEMORY" in ans.upper():
        return "REFUSED"
    v = oll(JUDGE.format(gold=gold, ans=ans)).upper()
    return "CORRECT" if "CORRECT" in v else "WRONG"


rows = json.load(open("evaluation/ras/posthoc_ablation_n16.json"))["rows"]
gold = {g["id"]: g["gold"] for g in json.load(open("/tmp/founder_gold.json"))}
by_frame = collections.defaultdict(list)
for i, r in enumerate(rows):
    by_frame[r["frame"]].append((i, r["question"]))

out = []
for fi, (frame, qs) in enumerate(by_frame.items()):
    path = f"{FRAMES}/{frame}"
    img = base64.b64encode(Path(path).read_bytes()).decode()
    derived = merge_text(oll(PERCEIVE, [img]), ocr_image(path))
    for i, q in qs:
        if i not in gold:
            continue
        ans = oll(STRICT.format(d=derived, q=q))
        v = judge(gold[i], ans)
        out.append({"id": i, "v": v, "gold": gold[i], "ans": ans})
        print(f"{i:2} {v:7} | gold: {gold[i][:32]:32} | sys: {ans[:38]}", flush=True)
    print(f"  [frame {fi+1}/{len(by_frame)} done]", flush=True)

c = collections.Counter(x["v"] for x in out)
n = len(out); cor, wr = c["CORRECT"], c["WRONG"]; ans_n = cor + wr
print("\n=== OCR-FIX + native-res, vs FOUNDER gold ===")
print("counts:", dict(c))
print(f"answerable_from_text: {cor/n:.3f}   hallucination: {wr/ans_n if ans_n else 0:.3f}   (n={n})")
print("baseline (crude pipeline) was: answerable 0.167, ~26 refused, ~11 wrong")
json.dump({"summary": dict(c), "answerable": round(cor/n, 3),
           "hallucination": round(wr/ans_n, 3) if ans_n else 0, "rows": out},
          open("evaluation/ras/ocr_rerun_foundergold.json", "w"), indent=2, ensure_ascii=False)
