#!/usr/bin/env python3
"""Probe the REAL brain (ask_home.ask) on the founder walk — does it match the
standalone consensus eval? Builds a kf_memory.json from the cached per-frame OCR
(each frame -> {t, frame, ocr}) and asks ask_home directly. Local only.

  .venv/bin/python evaluation/real_brain_probe.py [id ...]
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ask_home  # noqa: E402

MEMO = "/tmp/ocr_memory.json"
MODEL = "gemma3:12b-it-qat"
TEXT_IDS = {2, 4, 5, 7, 10, 22, 24, 25, 26, 33, 36, 40, 42, 43, 46}


def secs(name):
    m = re.search(r"_(\d+\.\d+)s", name)
    return float(m.group(1)) if m else 0.0


def build_kf():
    mem = json.load(open(MEMO))
    recs = []
    for frame, lines in mem.items():
        lines = [l for l in lines if l.strip()]
        recs.append({"t": secs(frame), "frame": frame, "caption": "", "ocr": lines})
    recs.sort(key=lambda r: r["t"])
    d = Path(tempfile.mkdtemp(prefix="walk_brain_"))
    (d / "kf_memory.json").write_text(json.dumps(recs, ensure_ascii=False))
    return str(d / "kf_memory.json")


def main():
    rows = json.load(open(ROOT / "evaluation/ras/posthoc_ablation_n16.json"))["rows"]
    gold = {g["id"]: g["gold"] for g in json.load(open("/tmp/founder_gold.json"))}
    want = set(int(a) for a in sys.argv[1:]) or TEXT_IDS
    path = build_kf()
    print(f"built walk kf_memory: {path}\n")
    for i, r in enumerate(rows):
        if i not in want or i not in gold:
            continue
        try:
            res = ask_home.ask(r["question"], path, model=MODEL)
            ans = (res or {}).get("answer", "")
        except Exception as e:
            ans = f"<ERROR {e!r}>"
        print(f"--- Q{i}: {r['question']}")
        print(f"    gold: {gold[i][:70]}")
        print(f"    REAL BRAIN: {ans[:160]}\n", flush=True)


if __name__ == "__main__":
    main()
