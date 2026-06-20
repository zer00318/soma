# CODEX BRIEF 7 — two-tier naming + honest renderer (lead, 2026-06-12 ~15:55)

Founder verdict on build 8baa5c7: map unreadable, cupboard misnamed as
refrigerator, positions wrong relative to genesis, words seem to vanish.
Lead diagnosis: device memory is FINE (59 objects persisted); the
"showing 4/46" declutter HIDES them. Misnaming is the architecture limit:
MobileCLIP-S0 zero-shot on coarse tiles scores 0.22-0.31 with ~0.01
margins — it guesses among CLIP-neighbors (cupboard/refrigerator/wardrobe).
A bigger vocab makes margins WORSE. Tuning will not fix this.

## P0 — ARCHITECTURE (lead decision): two-tier naming

Tier 1 (existing): MobileCLIP proposes a fast hypothesis word per region.
Tier 2 (new): FastVLM — ALREADY IN THE APP — verifies asynchronously.
- Trigger: object reaches sightings >= 3 and is unverified (or its
  MobileCLIP margin was < 0.02). Rate-limit: 1 verification in flight,
  cooldown ~5s; skip while thermal state is critical.
- Input: the saved region crop of the LAST sighting (highest-res crop you
  have for that object; add crop caching keyed by object id if needed).
- Prompt: strictly constrained, e.g. "One or two lowercase words: name the
  main solid object in this image. Answer with only the word(s)."
- Outcome: parse to a short word; if it differs from the MobileCLIP label,
  RELABEL the object (keep position/sightings; record old label in
  metadata.relabeled_from), set verified=true; post update to hub.
  Map shows verified words solid; unverified words dimmed/italic.
- This kills the cupboard→refrigerator class: VLM open naming is accurate
  where CLIP cosine is confusable; latency is hidden because it never
  blocks the scan loop.

## P1 — renderer honesty + navigation (founder demand)

- NEVER silently hide objects. Replace "showing 4/46" cap with:
  full word cloud + pinch-zoom + one-finger orbit + two-finger pan
  (founder: "hand tool to move through 3D space"). Cluster overlapping
  labels into expandable group chips ("5 words here" → tap to fan out)
  instead of dropping them.
- Label scale by distance, verified solid vs hypothesis dimmed.
- Debug strip stays (scan ms, namer p50/p95, hub ok/spooled, build).

## P2 — position sanity vs genesis

Founder reports positions wrong relative to genesis. Add to diag per
upsert: camera pose + raycast hit distance + plane id. Then a one-shot
analysis (scripts/analyze_spatial_diag.py extension) reporting per-word
position spread. If spread > 1m for static objects, raise promote
threshold to 3 sightings within 0.5m and surface position confidence
(sightings + spread) in /world payloads.

## Laws
- Build/install recipe per HANDOVER; bump nothing else. Stamp must show
  your commit. Python suite + north-star green if you touch soma_hub.
- ONE heavy job at a time on this Mac (memory-pressure reboots).
- When done: commit, install on device, relaunch, write results to
  ops/CODEX_BRIEF_7_RESULT.md (what you verified on device, diag evidence).
