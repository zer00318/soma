# SOMA Capture Pivot — Definitive Honest Assessment
**Date:** 2026-06-13 · **Capture:** `capture_20260613_041423` (home, 12 min) · **Walk analyzed:** OFFICE
**Build:** app `15caaf9` · device iPhone18,3 / iOS 27.0

> **Bottom line up front:** The phone-as-dumb-recorder side of the pivot is *unambiguously proven*. The Mac-understanding side shows a *massive density win* (~18x distinct objects) but its headline precision number is **not yet provable** — the clip_only adjudication that would convert "426 raw" into "N trusted" **was never produced**. Only the gemma_only verdicts exist. The defensible, evidence-bound trusted floor today is **152 objects** (the substring-agreed set), with a plausible-but-unverified ceiling near ~225.

---

## 1. PIVOT HARDWARE VERDICT — the phone works

From `capture_meta.json`, the 12-minute home capture:

| Metric | Value | Verdict |
|---|---|---|
| Battery | 80% → 80% | **0% drain** over 12.0 min |
| Thermal | 13/13 samples `nominal` (start, 11×minute, stop) | **Never left nominal** |
| Video | 3840×2160 @ 30 fps, 21,589 frames, **0 dropped** | Clean 4K |
| Poses | 7,197 (ARKit, ~10 Hz) | Continuous 6-DoF track |
| Duration | 720.3 s | Full session |
| Size | 1.08 GB | ~90 MB/min |

**Plainly: the phone-as-dumb-recorder works.** Zero measurable battery drain and a flat-nominal thermal trace across the entire run is the exact opposite of the realtime on-device build, which hit thermal pressure and the `hub ok:38 stuck` stall. Pushing all inference off-device reduced the phone's job to "capture 4K + poses and write to disk," and on that job it is boringly reliable: no dropped frames, no thermal escalation, negligible power. This is the single cleanest result in the dataset.

*Caveat for honesty:* battery reads in whole percent — "0% drain" means drain was below ~1 pt resolution over 12 min, not literally zero energy. Extrapolating a full hour at this rate is still safe (it would round to a few percent), but the 12-min number should not be quoted as "free forever." A 30–60 min capture should be run to confirm thermal stays nominal as the SoC soak-heats.

---

## 2. DENSITY — the multiplier

CLIP on the offline 4K walk produced:
- **426 distinct** object words (`clip_distinct`)
- **6,796 instance detections** (`clip_instances`)

The on-device realtime build managed **24 objects**. So the offline path delivers:

- **~17.8× more distinct objects** (426 / 24)
- **~283× more instance-detections** (6,796 / 24)

Even after the precision haircut below, the *floor* (152 trusted-agreed) is **6.3× the realtime build's 24**. The density thesis of the pivot — "stop starving perception on the phone's thermal/compute budget, let the Mac see everything" — is validated by a wide margin. There is no reading of this data where the offline path does not see dramatically more.

---

## 3. PRECISION — the honest cut (and the missing number)

**This is where I must be blunt: the number the brief asks for cannot be computed, because the adjudication it depends on does not exist.**

`/tmp/adjudication/` contains exactly one file — `gemma_only.json`. There are **no per-word verdicts for CLIP's 274 `clip_only` suspects**. The brief's formula —
`trusted = agreed_count + (clip_only adjudicated real)` and `halluc_rate = halluc / clip_only` —
both require clip_only verdicts that were never written. I will not fabricate them.

What *is* defensible from the data on disk:

- **Trusted floor = 152 objects.** The 152 substring-AGREED words are confirmed by two independent models (CLIP + gemma) seeing the same thing. This is the only set I can call trusted without hand-waving. Examples are mundane and correct for an office: `keyboard, monitor, desk, chair, laptop, cable, mouse, whiteboard, printer, router, power strip`.
- **426 raw is an upper bound, not a count.** The clip_only bucket (274 words) is where the hallucinations live, and it is large — bigger than the trusted set itself.

**Inspection-bounded estimate (explicitly NOT adjudication):** Reading the 274 clip_only words against "what plausibly sits in an office," ~146 are plausible (`wrist rest, soundbar, webcam, stylus, mirror, curtain rod, docking station, modem, scanner, earbuds, drill, glasses…`) and ~128 are office-implausible confabulations. If roughly half the clip_only survive real adjudication, trusted lands near **152 + ~73 ≈ 225**, implying a **CLIP clip_only hallucination rate near ~45–55%**. Treat 225 as a soft ceiling and ~50% as an order-of-magnitude halluc rate — both pending real verdicts.

**Funniest 5 CLIP hallucinations (office walk, with persistence):**
1. `bedpan` — and it is the **single most-detected clip_only word, 159 frames.** CLIP confabulated a bedpan more confidently than almost anything real.
2. `keg` (31) — no keg in the office.
3. `sword` (20) / `dagger` — armory in the cubicle.
4. `horse` / `saddle blanket` — a horse, indoors.
5. `bedpan`'s neighbors `razorblade` (152) and `cloak` (82) — both top-5 by frame count, both almost certainly wrong.

**Realest 5 CLIP-only saves (objects CLIP caught that the agreed set lacks):**
1. `wrist rest` (140 frames) — extremely plausible at a keyboard desk.
2. `soundbar` (101) — common on a monitor setup.
3. `webcam` (73) — plus `webcam cover` (27).
4. `docking station` (30) / `modem` — real office IT.
5. `stylus` (62) — pairs with the agreed `graphics tablet`.

These five are exactly why clip_only adjudication is worth doing: real recall is hiding in that bucket alongside the bedpans. **The headline "trusted objects" number stays unprovable until those 274 words get verdicts.**

---

## 4. RECALL GAP — objects even CLIP missed

From the one adjudication that *does* exist (`gemma_only.json`, 29 words), gemma found **10 real objects CLIP never named** — the vocab-addition list:

> **carpet, footrest, cabinet, server, corkboard, notebook, sign, container, hanger, cup**

The other 19 gemma_only words were correctly judged non-objects: structural surfaces (`floor`, `screen`), abstract content (`drawing(s)`, `text`, `icons`, `plans`, `photos`, `documents`), fragments (`legs`, `metal bar`, `cork`), and vague descriptors (`white device`, `apple device`, `equipment`, `label`, `printout`, `papers`, `document`).

So the recall gap is real but small and concrete: **10 nameable objects** — mostly furniture (`cabinet`, `footrest`, `hanger`), IT (`server`), surfaces (`corkboard`), and everyday items (`cup`, `notebook`, `container`, `sign`, `carpet`) — that belong in the CLIP vocabulary.

---

## 5. VERDICT — is offline-Mac-understanding the right architecture?

**Yes, on the evidence, with one unfinished step.** The phone side is proven clean (0% battery, flat-nominal thermal, 21,589 4K frames + 7,197 poses, zero drops) — it decisively beats the realtime build that thermal-throttled and stalled. The Mac side sees ~18× more distinct objects, and the 152-object agreed floor alone is already 6.3× what the device managed, so the density premise holds even under the harshest precision discount. The architecture is sound; the data supports committing to it. The honest asterisk is that the headline *trusted-object* number is still a floor (152) with an unverified ceiling (~225) because the clip_only adjudication that would settle it was never run — and CLIP's clip_only bucket is visibly ~half junk (`bedpan` at 159 frames is the loudest tell). The pivot is right; its precision claim is simply not yet finished.

**Single change that would most raise trusted-object count next:** **Run the clip_only adjudication** (verdicts for all 274 clip_only words, same format as `gemma_only.json`). That one step converts "426 raw / 152 proven floor" into a defensible trusted count, recovers the real saves (`wrist rest`, `soundbar`, `webcam`, `docking station`, `stylus`) out of the bedpan noise, and is the gate on every downstream precision claim. After that, add the 10 gemma_only reals to the vocabulary to close the recall gap.

---

### SCORECARD
`PIVOT: phone ok, density 18x, trusted ~152 objects, CLIP precision ~50%`

*Notes on the scorecard numbers:* `phone ok` = 0% battery drain + all-nominal thermal. `density 18x` = 426 distinct / 24 realtime. `trusted ~152` = the **proven floor** (substring-agreed); the brief's full formula could not be evaluated because clip_only adjudication does not exist — soft ceiling ~225 if ~half of clip_only adjudicate real. `CLIP precision ~50%` = inspection-bounded estimate of clip_only survival, **not** measured (no verdicts on disk); reported as an explicit estimate, not a result.
