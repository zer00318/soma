# Enrichment scheduler — design (2026-06-10)

Core engine per strategy redirect: cheap always-on detector → salience →
budget-governed VLM enrichment. "Coarse passerby / fine fixation."

## Placement

In-process library (`soma_perception/scheduler.py`), no server. The phone is
the compute node; the Python implementation drives the mac simulator and the
algorithm must be portable to Swift 1:1 (no Python-only dependencies in the
core logic).

## Pipeline

1. **Detector loop** (always on, cheap): YOLO/Vision detections per frame →
   track stubs (id, class, bbox, first/last_seen).
2. **Salience score** per track, computed every tick:
   - `dwell`: seconds in view, saturating (sigmoid at ~8s). Passersby score low.
   - `novelty`: 1 - similarity to what the graph already knows (class+place
     co-occurrence lookup; later: contextual keys). Familiar desk objects ≈ 0.
   - `stability`: scene motion inverse — enrichment of a blurry pan is wasted.
   - `salience = dwell_progress * (0.6*novelty + 0.4*stability)` — dwell GATES
     (multiplicative): a brand-new track scores ~0 regardless of novelty, so
     passersby can't burn budget. (Revised from additive during step 1; the
     additive form let novelty+stability alone clear the threshold.)
   - **Progressive enrichment ladder** (core product idea: attention depth =
     knowledge depth): levels overview → attributes → minutiae, requiring
     8s / 24s / 72s accumulated dwell respectively (3x escalation), one
     budget token each, capped at 3. dwell_progress is measured against the
     NEXT level's requirement, so a freshly-enriched subject cools down and
     only sustained fixation earns the deeper pass (the toy's color first;
     the paint peel and scratches only after real attention). The VLM
     consumer varies its prompt by `detail_focus` and writes DELTA facts
     ("note details not yet recorded") to the graph with provenance.
3. **Budget governor** (the moat — all-day battery):
   - Token bucket: N VLM calls per hour (hard ceiling), refill continuous.
   - A salient track CONSUMES a token only when it wins the queue; queue is
     max-salience, not FIFO; stale entries (>60s out of view) evicted.
   - Thermal/energy hook: bucket size scales down on thermal pressure
     (ProcessInfo.thermalState on iOS; stub on mac).
4. **Enrichment call**: existing FastVLM/`vlm_enrich` path, 12s timeout,
   result → graph via confidence gate + event dedup (already live).

## Metrics (must log from day one)

- enrichments/hour vs ceiling, salience distribution, queue evictions,
  % enrichments that produced novel graph facts (ties into north-star eval).

## Build order

1. `scheduler.py` with injected clock + fake detector (pure-logic unittests).
2. Wire into `soma_perception/worker.py` mac loop behind a flag.
3. Budget proof: 8h mac run, log enrichments/hour + facts-novel rate.
4. Port to Swift in FastVLM app once Python numbers hold.
