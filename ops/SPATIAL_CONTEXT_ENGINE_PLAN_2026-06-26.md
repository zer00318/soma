# Spatial Context Engine — Architecture & Plan (2026-06-26)

**Decided with the founder this session. This supersedes the "answer from text descriptions"
binder model. The middle of the stack is being rebuilt around world-anchored instances.**

## The goal (the only yardstick)

**Context acquisition: maximize the fraction of the lived scene faithfully preserved as text.**
Three axes, in order: **coverage** (how many things / attributes / relations captured),
**fidelity** (correct, not invented), **richness** (depth per thing). Every design choice is
judged on "how much correct scene does this let us preserve," not on ease of build.

## The core reframe (founder's, 2026-06-26)

Nothing in the helper or binder layer ever **counts** or asserts "5 jars." Instead:

1. **Localize** every instance as a region in a **shared world coordinate frame** —
   *from where to where* it occupies space. That location IS the identity substrate.
2. **Describe** each instance with a parallel fan-out of attribute readers
   (label, colour/material, orientation, state: empty/full, size). An instance is a node:
   `{world_xyz, mask, type, attrs[]}`. A second jar at a *different location* is a
   *different node* even if described identically.
3. The **binder assembles a graph**, it does not count. Instances are individuated by
   **location**; relations ("on top of", "next to", "on the bed") are **derived from
   geometry**, deterministically. No LLM in this step.
4. The **LLM does meta-commentary** over the graph: count = number of jar nodes; "which is
   on top" = read an edge; "which ring has the gemstone" = read a node attribute.
   **Counting and spatial reasoning become derivations, never guesses.**

This kills four gaps at once: counting (derived), empty/full (per-instance attribute),
spatial relations (free from geometry), and cross-frame **double-counting** (same world
location across frames = one node).

## Decisions locked

| Question | Decision |
| --- | --- |
| Perceiver | **Both** — stronger VLM for macro+identity AND specialist helpers |
| Localizer | **Open-vocab detector (Grounding-DINO) + SAM2** (class-agnostic masks + tracking) → per-instance attribute VLM |
| Spatial backbone | **Ride ARKit** (visual-inertial world tracking + ARWorldMap persistence + depth) + layer visual relocalization for the indoor macro anchor |
| Spatial layer shape | **One unified world reconstruction** fed by sub-helpers (pose, depth, altitude, GPS, localizer) — persistent across motion / frame-cuts / shutdown. NOT a separate 2D system. |
| Geometry | **2D + depth**, but as part of the unified suite (ARKit carries it) |
| Executor autonomy | **Propose-only** — workers gate against an isolated copy, green patches queued for Chief review |
| North-star metric | **Fraction of scene preserved = coverage × fidelity** (replaces the 11-question Q&A as the primary eval) |

## Target architecture

```
DEVICE (iPhone, ARKit) — emits ONLY derived text/numbers; frames+crops transient
  spatial backbone:  ARKit world tracking (6DOF pose) + depth + ARWorldMap persistence
  macro anchor:      GPS + barometer (+ visual relocalization indoors)
  per frame:
     detector (open-vocab boxes) ─┐
     SAM2 (masks + tracking)  ────┤→ instances {mask, tracklet_id}
     per instance (PARALLEL):     │
        attribute VLM on clean mask-crop → {label, colour, material, orientation, state, size}
     ARKit lifts mask centroid + depth → WORLD coordinate, drops/updates an anchor
  → derived records: {instance_id, world_xyz, mask_box, type, attrs[], t}

MAC BRAIN (unbounded)
  INJECT v2: world-anchored instance GRAPH
     nodes = instances (world coord + attrs), individuated by world location
     edges = relations from world geometry (on-top-of, next-to, in/on, behind)
     temporal: same world location across frames → same node (no double-count)
  LLM meta-reasoner over the graph → two-zone honest answer
```

## Phases — each one verifiable, with a real test (LEASH)

**P0 — Honest executor + spec (DONE this session).**
Real test gate, propose-only worker, `tests/test_inject_structure.py` acceptance spec,
tablecloth hallucination fixed + verified end-to-end, ops single-owner stabilized.

**P1 — Persistence slice (the falsifiable core). BUILD FIRST.**
ARKit world tracking on; a cheap detector finds one object; drop an ARAnchor at its world
position. **TEST: move the camera away and back — the object must read as the SAME node at
the SAME world spot (within tolerance), one instance not N.** Metric: anchor stability under
N frames of motion. If it fails (e.g. white-wall drift), we learn before building on top.
*Prerequisite check: confirm iPhone 17 model (LiDAR?) and on-device compute budget.*

**P2 — Detector + SAM2 instance extraction (coverage + precision).**
Open-vocab detector + SAM2 masks + tracking; each instance = mask + tracklet + world coord.
**TEST: instance coverage % and boundary IoU vs human-labelled instances on a real capture.**
This is where the north-star coverage metric goes live. Cadence: detector every frame, SAM2
at keyframes, light SAM variant if thermal forces it.

**P3 — Per-instance parallel attribute fan-out (richness).**
Parallel readers per clean mask-crop: label OCR, colour/material, orientation, state, size.
**TEST: per-instance attribute accuracy vs ground truth** (the "con peperoncino, 195g" and
"empty/full" cases).

**P4 — INJECT v2: world-anchored graph + geometric relations.**
Binder assembles nodes + edges from world geometry; temporal individuation by location.
**TEST: relation accuracy ("which jar on top", "pesto next to nutella"), count-by-derivation,
zero double-count across frames.**

**P5 — LLM meta-reasoner + north-star eval at scale.**
LLM answers count/spatial/attribute from the graph. **TEST: ground-truth eval at n≥100 across
several real captures + coverage×fidelity score.**

## The salience / "what's interesting here" axis (founder, 2026-06-26)

The enumerative helpers (detector → instances → attributes → OCR) inventory the EXPECTED.
They have a structural blind spot for the UNEXPECTED — often the most human-valuable context.
Add a PARALLEL salience helper (`scripts/salience_helper.py`) that only adds what they miss,
TIERED so it never contaminates ground truth:
- **observed** — a concrete visible anomaly/condition (dirt on a keyboard, a crack, wear)
- **recognized** — an entity identified by APPEARANCE not OCR (a known person/brand/landmark)
  → triggers the existing EXPAND world-knowledge layer (the 'looked up Kushal Mehra with no
  on-screen text' case). Binding carries recognition confidence — hedge it.
- **inferred** — a speculative/interesting guess, clearly hedged.

Coverage axes the enumerative stack still misses (the map this opened up):
1. anomaly/condition (dirt, wear, damage, freshness) — not in the attribute schema
2. recognition + world-knowledge (entity by appearance → enrich)
3. salience/relevance (what a person would notice/remember in THIS frame)
4. dynamics/events (appeared/disappeared/moved/screen-changed/hand-action — needs frame pairs)
5. affordance/function/ownership (what's it for, whose is it)
6. text UNDERSTANDING (not just OCR — what the text MEANS)
7. self/embodiment (what the WEARER is doing — first-person activity)
8. social/affect (who's present, mood, social dynamics)

Design rule: salience is confabulation-prone, so it lives in its OWN fenced tier and never
asserts as 'seen'. The tiering keeps it honest. Recognition egress stays in the privacy moat
(derived text only) but the binding is hedged.

## Division of labor

- **Local LLMs (propose-only):** menial deterministic Python against acceptance tests —
  INJECT v2 graph assembly, relation geometry, the eval scorer, glue code. Each task ships
  with its acceptance test = the spec. Gate against an isolated copy; Chief reviews/merges.
- **Chief:** architecture, the iOS/ARKit + detector/SAM2 integration (structural), reviewing
  worker patches, verification.
- **Founder:** real captures + ground truth, direction.

## Privacy moat (re-assert every phase)

Only derived **text and numbers** ever persist or leave: instance ids, world coordinates,
mask boxes, attributes. Masks, crops, frames, poses-of-raw are **transient** — read then
dropped. No raw media stored or transmitted. A world coordinate is derived metadata, not media.

## Immediate Chief tasks before unpausing the executor

1. Make the worker **copy-safe** — gate against an isolated worktree/copy, never mutate live
   source during gating. (Worker is paused via `ops/worker_paused` until this lands.)
2. Confirm device capability (LiDAR / compute) for P1.
3. Re-scope worker tasks to **complete named functions** (the splicer can't edit fragments).
