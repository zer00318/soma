# CODEX BRIEF 12 — trusted naming: gate hallucinations out of the world

Lead-finalized from the audit draft (2026-06-13, ultracode marathon).
The capture pivot is HW-validated (12min 4K, 0% battery, nominal thermal,
7197 poses). The offline Mac pipeline produced a 408-object HOME world and
a 426-object OFFICE inventory — but cross-check vs gemma proves CLIP
forced-choice is ~50% hallucination (bedpan/razorblade/sword in an
office). This brief replaces CLIP-as-final-namer with gemma-confirmed
naming + abstention, and RE-NAMES the home world so it becomes trustworthy.

## BUDGET / LAWS (read before coding)
- P0 then P1, commit per P (if .git read-only in your sandbox: leave
  uncommitted + LOUD warning in RESULT). Stop after P1.
- One-heavy-job law: gemma3:12b on ollama is GPU — run it SERIAL, never
  alongside another GPU job (two reboots from memory pressure historically).
- Suite + north-star green after any soma_hub change
  (python3 -m unittest discover -s tests -p "test_*.py";
   python3 evaluation/run_north_star.py).
- X-SOMA-Token; data/soma_hub.sqlite3; with self._connect(); no Flask.
- Mac-side scripts use .venv/bin/python (cv2/torch/open_clip live there).
- The honest trusted-object COUNT is the founder deliverable, not raw
  density. Turn 408 noisy home objects into a smaller defensible number.

## ACCEPTANCE (lead-verifiable, on REAL data not just self-test)
1. scripts/walk_name_objects.py runs on /tmp/walk_labels.json (office) and
   on /tmp/home_labels.json (home), emitting trust-tiered named objects.
2. Re-built HOME world: /tmp/home_named.json -> inventory -> fuse -> a
   TRUSTED home world JSON; bedpan/razorblade-class words gone or marked
   untrusted; trusted count printed and far below 408.
3. The 10 gemma-only real words appended to ops/spatial_vocab.txt
   (carpet, footrest, cabinet, server, corkboard, notebook, sign,
   container, hanger, cup) — embeddings rebuild is the LEAD's step, just
   append the vocab.
4. world3d renders trusted solid, lower tiers translucent; phantoms gone.
5. RESULT file ops/CODEX_BRIEF_12_RESULT.md with measured before/after
   trusted counts on the home walk.

---

## Why (the audit, measured — not assumed)

Office walk, `/tmp/reconcile_buckets.json`:
- CLIP forced-choice produced **426 distinct labels / 6796 instances**.
- Cross-checked against gemma's independent 280-frame describe:
  - **152 agreed** (36% of CLIP-distinct) — the trustworthy core.
  - **274 CLIP-only** (64%) — forced-choice cosine garbage. Worst part:
    these hallucinations carry HIGH instance counts (`bedpan` 159,
    `razorblade` 152, `wrist rest` 140, `iron` 137, `cloak`, `saucer`)
    in an office. Count-weighting in fusion makes them LOUDER, not quieter.
  - **29 gemma-only** real things CLIP could never say because they are
    not in vocab (`carpet`, `cabinet`, `corkboard`, `server`, `footrest`,
    `notebook`).

CLIP precision is ~half. CLIP's argmax over the whole vocab NEVER abstains
— `walk_label_crops.py` always emits `vocab[sim.argmax()]`, so a crop of a
blank wall returns the nearest vocab word with a plausible cosine. That is
the root cause of phantom objects in `/world3d`. gemma is more reliable at
naming (open-vocab, can say "I don't recognize a discrete object") but
~50-200x slower per crop, so it cannot label all 6796 crops directly.

## Options considered

- **(a) gemma as primary namer, CLIP as fast pre-filter.** Highest
  precision. CLIP narrows 6796 crops to a candidate shortlist + proposes a
  word; gemma confirms/renames/rejects only the survivors. Cost is bounded
  because gemma runs on hundreds, not thousands, of crops.
- **(b) Two-model agreement gate.** Object enters the world only if CLIP
  and gemma independently name it (the 152 "agreed" bucket). Simple,
  cheap, very high precision — but throws away the 29 gemma-only real
  objects and any object gemma's frame-level describe happened to miss.
  Good as a TRUST TIER, not as the whole namer.
- **(c) Add the 29 gemma-only words to vocab.** Cheap, strictly additive
  recall win, but does NOTHING about the 274 false positives — and a
  bigger vocab gives forced-choice MORE wrong answers to pick from. Helper,
  not a fix.

## DECISION — P0 is (a), with (b) as the trust label and (c) folded in

(a) is the highest-leverage move: it attacks the 64% false-positive mass
directly while keeping CLIP's speed where speed matters (the shortlist).
(b) becomes a per-object `trust` field rather than a separate pipeline.
(c) is a one-line vocab append done alongside, for free recall.

The founder deliverable is an **honest trusted-object count**, not raw
density. Brief 11 gave 426 "objects" that are 64% noise. This brief should
turn that into a smaller number we can defend object-by-object.

---

## P0 — gemma-confirmed naming: `scripts/walk_name_objects.py` (new, Mac-side)

CLIP pre-filter -> gemma confirm/rename -> trust-tiered labels. Sits
BETWEEN `walk_label_crops.py` and `walk_build_inventory.py`. CLIP output
is now a CANDIDATE, never a final label.

Inputs: `--labels /tmp/walk_labels.json` (CLIP candidates w/ crop_path +
score), `--crops-dir`, `--vocab ops/spatial_vocab.txt`,
`--out /tmp/walk_named.json`.

Pipeline per crop:
1. **CLIP pre-filter (cheap, already computed).** Keep crops whose CLIP
   score >= floor. Drop crops below the floor as "no confident object"
   (do NOT force a word). This alone kills the blank-wall phantoms.
2. **gemma confirm (bounded).** For each surviving crop, ask gemma3:12b
   (ollama, one-heavy-job law: serial, no GPU contention) a CLOSED
   question: "Here is a cropped object. Is this a <CLIP word>? If not,
   name it in 1-3 plain words, or answer NONE if it is not a distinct
   object." Temperature 0, refusal-default. Parse to `gemma_label` or
   `NONE`.
3. **Trust tiering** per crop -> object:
   - `trusted` — CLIP word == gemma word (or gemma confirms): the 152-style
     agreement. Render solid in `/world3d`.
   - `gemma_named` — gemma overrode CLIP with a different real word
     (recovers `cabinet`/`corkboard`-style): trusted, render solid.
   - `clip_only` — gemma said NONE / disagreed with no replacement: DROP
     from the world (recall-only at most). This is where `bedpan` dies.
   Emit `name_source: clip_agreed|gemma_named|clip_only` and
   `trust: trusted|rejected` on every record.
4. Fold in **(c)**: append the gemma-only real words
   (`/tmp/reconcile_buckets.json` -> `gemma_only`, the office-grounded set:
   carpet, cabinet, corkboard, server, footrest, notebook, drawing,
   documents, screen, legs, floor, ...) to `ops/spatial_vocab.txt` in the
   same PR, deduped, so the next CLIP pass has a shot at them too.

Wiring:
- `walk_build_inventory.py` and `walk_fuse_world.py` consume the NAMED file
  and **only fuse `trust: trusted` records into 3D**. Rejected records may
  still ride into positionless recall inventory, never into `/world3d`.
- One-heavy-job law: gemma runs serial on the GPU; CLIP and fusion are
  CPU/JSON. Watchdog + progress to stderr like `walk_label_crops.py`.
- `--self-test` (no files, no models): stub CLIP candidates + stub gemma
  responder; assert an agreed crop -> trusted, a gemma-override -> trusted
  with new word, a NONE -> rejected/not-fused. SELF-TEST PASS / exit codes.

### P0 acceptance criteria (measured, not asserted)

- On the office walk, re-run end to end and report in
  `ops/CODEX_BRIEF_12_RESULT.md`:
  - **Trusted distinct object count** (the founder number) and how it
    compares to the 426 raw / 152 agreed baseline. Target: the world is
    built from trusted+gemma_named only, NOT the 426.
  - **False-positive kill rate:** of the 274 known CLIP-only suspects
    (`bedpan`, `razorblade`, `cloak`, `iron`, `saucer`...), >= 90% must be
    `rejected` (not fused). Name any that survive and why.
  - **Recall recovered:** how many of the 29 gemma-only words now appear
    as `gemma_named` objects (e.g. cabinet, corkboard, server). Target
    >= half.
- `/world3d` on the pose-bearing home capture renders ONLY trusted objects;
  manually spot-check that no obvious phantom (an office/clinical word in a
  home, etc.) is pinned in space.
- gemma pass stays within a sane wall-clock budget on the office crop set
  (report the number; CLIP pre-filter must cut the gemma call count by a
  large factor vs 6796 — report the actual survivor count).
- Suite + north-star green after any soma_hub/ingest changes. No new GPU
  contention (one-heavy-job law upheld).

## P1 — make trust visible in the world + recall

- `/api/world` + `/world3d`: carry `trust` and `name_source` per object;
  render `trusted` solid, leave rejected objects out of render entirely
  (recall-only). Offline-positioned-but-trusted objects keep brief 11's
  slight transparency (inferred depth), but NO transparency tier for
  rejected — they simply do not render.
- Recall answer for "where is X" must never cite a `rejected` object as a
  located thing.
- Tests: fixture with one trusted positioned object + one rejected object;
  assert only the trusted one reaches `/world3d`; assert the rejected one
  is absent from spatial recall. Suite + north-star green.

RESULT: `ops/CODEX_BRIEF_12_RESULT.md` — trusted object count vs baseline,
false-positive kill rate on the 274 suspects, recall recovered from the 29
gemma-only words, gemma wall-clock, and what the lead must eyeball in
`/world3d` before trusting it.
