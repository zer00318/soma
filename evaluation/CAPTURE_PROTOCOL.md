# Bigger-capture protocol — the gate to a number we can bet on

n=15 (the `walk_outside_20260614` text subset) is too small to trust: one question = 6.7%.
Before "pitch-ready", we need ~50 reading questions on a fresh, text-rich walk, scored vs
**your** human gold. This is the one step that needs you (Satoshi). Everything else is wired.

## 1. Record a TEXT-RICH walk (the product is "a memory for everything you READ")
Phone, first-person, ~2–4 min. Walk SLOWLY past text you'd actually want to remember reading:
- street signs, building plaques, room/door labels, transit boards, posters, menus, price tags,
  product labels, a screen or two, a document/whiteboard. Pause ~2s on each so the camera reads it
  from a few angles (the consensus needs 3+ frames per sign — walking past too fast starves it).
- Mix easy (large print) and hard (small/cursive/angled) so the honesty gate is real, not gamed.

## 2. Extract frames (local)
```
.venv/bin/python scripts/walk_extract_frames.py --video <your.mov> \
    --out data/walks/<walk_name>/work/run_frames --fps 2 --min-sharpness 40
```

## 3. Generate post-hoc questions + candidate gold (local, gemma)
```
.venv/bin/python evaluation/posthoc_ablation.py \
    --frames-dir data/walks/<walk_name>/work/run_frames \
    --n 25 --k 2 --strict --out evaluation/ras/<walk_name>_ablation.json
```
`--n 25 --k 2` ≈ 50 questions. (Auto-gold is unreliable on fine text — you fix it in step 4.)

## 4. Confirm YOUR gold in the browser (5–10 min, the only manual step)
```
# point make_gold_review.py SRC at <walk_name>_ablation.json, then:
.venv/bin/python evaluation/make_gold_review.py
open evaluation/gold_review.html
```
For each frame: type the TRUE answer (or mark not-answerable-from-this-frame). Export → save the
JSON (e.g. `/tmp/founder_gold_<walk>.json`). This is the ground truth the gate is scored against.

## 5. Score the honest number (local; 27b answerer for recall)
Point `ocr_recall.py` at the new frames + gold (FRAMES / gold path / TEXT_IDS), then:
```
.venv/bin/python evaluation/ocr_recall.py --model gemma3:27b-it-qat --half 5 --minrep 3
```
Gate: **≥60% correct AND <10% wrong** on the reading subset. With n≈50 this is a number to bet on.

## What "good" looks like
The hallucination rate is the moat — wrong-of-answered must stay near zero (the system refuses what it
can't read). If correct% is low but wrong% is also near zero, that's an HONEST early product (upgrade the
eyes); if wrong% is high, that's the failure we will NOT ship. See `ops/HANDOFF_STATE.md` /
`memory/trace-consensus-recall.md`.
