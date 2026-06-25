# CODEX BRIEF 6 — spatial post pipeline dead + mega-vocab (lead, 2026-06-12 ~15:00)

## P0 — spatial posts silently never fire (REGRESSION, blocks everything hub-side)

Evidence (lead-verified, build 29cc439 on device):
- Founder scan 14:35–14:38 local, 12 words on the phone map, hub DOWN
  (Mac rebooted 14:17; stack restarted by lead 14:47).
- Status line showed `hub ok:0 spooled:0` the whole time.
- Device spool pulled at 14:50: 58 packets, ALL `native_vision` (main
  capture path spools fine), ZERO `mobileclip_spatial_word` lines.
- Conclusion: `postSpatialSnapshotIfNeeded()` (SpatialWorld.swift ~1207,
  called from ~585 and ~1154) never executes its post/spool branch, or an
  early guard always returns. Candidates to check: `words` empty at call
  time vs render copy; the signature/8s guard interacting with both call
  sites; MainActor/queue issues; iOS Local Network permission denial path.
- Add a `spatial_post` decision line to spatial_diag.ndjson on EVERY call
  (posted/spooled/skipped+reason) so this class of failure is measurable.

Acceptance (lead verifies via cable pull):
1. Hub up + Spatial mode scanning → status `hub ok` climbs, hub access
   log shows phone POSTs, /world updates live.
2. Airplane mode scan → `spooled` climbs, spool gains spatial lines,
   replay lands them.

## P1 — mega-vocab: stop spoon-feeding words

196 hand-words is still a toy. Plug-and-play label sets exist:
- Merge LVIS category names (1203), OpenImages classes, and our 196 into
  `ops/spatial_vocab.txt` (lowercase, dedup, filter to physical indoor/
  carry objects — delegate the relevance filter to the local LLM at
  127.0.0.1:1234, batched, NOT by hand).
- Target ~800–1500 words. Rebuild via scripts/build_vocab_embeddings.py
  (.venv python; checkpoint already at models/mobileclip/mobileclip_s0.pt).
- CRITICAL: margin floor 0.02 was tuned for 82 words. With ~1000+ words
  margins shrink mechanically. Recalibrate: take vocab_misses.ndjson +
  spatial_diag.ndjson from the last scans, recompute score/margin
  percentiles, set floors so the known-correct words (laptop, keyboard,
  mouse, webcam, desk...) still pass. Likely margin→~0.005–0.01, keep
  score floor ~0.22. Make both floors UserDefaults-overridable so tuning
  needs no rebuild.
3. Acceptance: desk scan names a POWER BANK (the founder's litmus), and
   p50 naming latency stays <200ms at the larger vocab (it's one matmul —
   if it regresses, batch the cosine in MPS/Accelerate).

## P2 — Mac stack must survive reboot

Today's "no progress" was the Mac rebooting and killing hub+enricher.
launchd LaunchAgent fails with TCC "Operation not permitted" on Documents.
Find the clean path (move a small supervisor outside ~/Documents that the
TCC allows, or document the one-time founder grant). Acceptance: reboot →
hub /health 200 within 2 min, no human.

## UPDATE (lead, 2026-06-12 ~15:25) — P0 DONE by lead; P1 now fully yours

- P0 is FIXED and device-verified (commit 391aac8): root cause was
  non-finite floats invalidating JSONSerialization silently. Post outcomes
  now logged as `__post__` diag lines. Do NOT redo this.
- NEW FINDING: office Wi-Fi has client isolation → live posts always spool
  there. `scripts/cable_sync_spool.sh [sec]` (nohup, restart after reboot)
  pulls+replays+truncates over USB. Works.
- NEW FINDING: hub-side `_touch_spatial_entity` rewrote label/label_norm
  and collided with UNIQUE(kind,label_norm) → 1591/1592 replayed packets
  failed. Lead fixed (touch updates liveness only); 171/171 packets now
  ingest on a copied DB. Suite gate running; lead commits.
- P1 mega-vocab is now END-TO-END yours, including the grunt loop:
  1. Fetch LVIS classes: raw.githubusercontent.com/ultralytics/ultralytics/
     main/ultralytics/cfg/datasets/lvis.yaml (1203 names, take first
     synonym before '/'). /tmp was wiped by reboot — refetch.
  2. Filter for indoor/home/office/carry relevance with the LOCAL LLM
     (trace-local-worker on 127.0.0.1:1234, temp 0, batches of ~60).
     RUN IT ALONE: no concurrent xcodebuild/replay/enricher-heavy work —
     the 15:15 Mac hang was concurrent load (memory pressure). One heavy
     job at a time on this machine.
  3. Merge with ops/spatial_vocab.txt (196), dedup near-synonyms, rebuild
     embeddings, verify bundle count, build+install per HANDOVER recipe.
  4. Margin floor: make score/margin floors UserDefaults-overridable and
     recalibrate from spatial_diag so known-correct desk words still pass
     at the bigger vocab.
- DEVICE DUP REGRESSION to investigate with P4: device world now holds
  'fan' x2 and 'keyboard' x2 (pull spatial_world.json to confirm) — the
  same-word merge radius failed across sessions or across relocalization.
  Also founder reports a power bank in view that never gets named; current
  world has 'phone case' — possibly the power bank misnamed (CLIP
  confusion). After mega-vocab install, check its score/margin in diag.
