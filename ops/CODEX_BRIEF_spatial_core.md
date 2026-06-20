# CODEX BRIEF — Spatial Object Permanence Core (priority task #8)

Written by Claude (lead) 2026-06-11 late. This is the ONLY priority per
founder redirect: instant object naming + fixed coordinates + permanent
memory. Attributes/chat/OCR/episodes are all secondary until this works.
Founder's words: "We want to record WORDS not prose. Something that
quickly identifies and names objects." No YOLO (80 closed classes), no
FastVLM in the naming loop (seconds-slow, rambles).

## Acceptance (founder-testable, in this order)

1. Point phone at desk: within ~1–2s per object, single WORDS (cpu, fan,
   keyboard, mouse, monitor, bottle…) appear pinned at 3D positions,
   visible live in the app AND at http://localhost:8777/world.
2. Objects are PERMANENT: re-seeing increments a sightings counter and
   refines position; nothing ever decays or disappears.
3. Kill the app, reopen in the same room: the word map reloads and
   relocalizes (positions line up again).

## Architecture — MobileCLIP zero-shot naming (the YOLO↔FastVLM middle)

Pipeline per scanned frame (replaces the FastVLM word scanner inside
SpatialWorld.swift's scanSync — engine skeleton already exists):

1. REGION PROPOSALS (no vocabulary, fast):
   `VNGenerateObjectnessBasedSaliencyImageRequest` → up to ~3 salient
   rects per frame. That's enough; the scanner runs ~1/s and the user
   pans. (Plane-protrusion proposals can come later; NOT required.)
2. NAMING (ms-fast, words-only): MobileCLIP-S0 image encoder, CoreML.
   - Crop each region from the pixel buffer, resize to the encoder's
     input (256×256), run encoder → 512-d embedding.
   - Cosine-similarity against PRECOMPUTED word embeddings; take the top
     word if margin over runner-up > 0.02 and score above tuned floor
     (start ~0.22, tune on the founder's desk).
   - KEY SIMPLIFICATION: do NOT ship the text encoder. Precompute word
     embeddings OFFLINE once (step A below) into a bundled JSON.
3. PINNING (works WITHOUT LiDAR — founder's iPhone 17 base has none):
   existing `position(for:frame:)` raycast against `.estimatedPlane`
   gives genesis-frame coords. Extent: raycast the region's corner
   points too; width = distance between corner hits (best effort, OK to
   skip in v1).
4. PERMANENCE:
   - In-engine: upsert by (word, within 0.4 m) → sightings += 1,
     position = EMA(0.8·old + 0.2·new). NEVER delete.
   - Disk: serialize objects to JSON in the app container
     (Application Support/SOMA/spatial_world.json); load on start.
   - ARWorldMap: save on stop, load+relocalize on start (same room).
   - Hub: keep posting the spatial snapshot (already implemented —
     postSpatialSnapshotIfNeeded) so /world renders progress.

## Work order

A. OFFLINE (Mac, python): get apple/ml-mobileclip (MobileCLIP-S0).
   - `pip install mobileclip` (or build from the repo) in .venv.
   - Script `scripts/build_vocab_embeddings.py`: read
     `ops/spatial_vocab.txt` (one word per line), run the TEXT encoder,
     L2-normalize, write `soma-native-fastvlm/FastVLM App/Resources/
     vocab_embeddings.json` as {"word": [512 floats], ...}.
   - Convert the IMAGE encoder to CoreML (.mlpackage) with coremltools
     (target iOS17+, ANE). Add to the Xcode project.
B. SWIFT: `MobileCLIPNamer.swift` — loads .mlpackage + JSON, exposes
   `name(crop: CVPixelBuffer) -> (word: String, score: Float)?`.
C. SWIFT: in SpatialWorld scanner, replace the FastVLM call with
   saliency rects → namer → existing finishWordScan flow (labels +
   screen points — the raycast/upsert path is already there).
D. PERMANENCE: JSON persistence + ARWorldMap save/load + never-decay
   upsert (cap position EMA, keep sightings).
E. MEASURE + SHOW: log ms/frame and words/min to the on-screen status;
   founder verifies at /world. Tune score floor on his desk (cpu, fan,
   keyboard, mouse MUST name correctly — that was the failing test).

## Constraints (project law — do not violate)

- Auth header X-SOMA-Token; DB soma_hub.sqlite3; no Flask; never Apple
  ID/password. Build: -sdk iphoneos26.5 + ASSETCATALOG_EXEC=
  /tmp/actool_wrapper/actool (recreate after reboot). Device
  D3A506B2-8923-5313-B8A3-FF769ABBA228, bundle de.zer00.soma.
- FastVLM stays in the app for SPARSE enrichment later — just not in
  the naming loop.
- Claude's sessions are limit-constrained; this brief is the contract.
  If something here is wrong in practice, write findings into
  ops/HANDOVER.md so the next Claude session sees them.

## Vocabulary starter (ops/spatial_vocab.txt)

desk, chair, monitor, keyboard, mouse, cpu tower, laptop, headphones,
phone, tablet, lamp, fan, bottle, mug, glass, plate, book, notebook,
pen, scale ruler, scissors, charger, cable, power strip, webcam,
microphone, speaker, router, printer, backpack, jacket, shoe, door,
window, curtain, shelf, drawer, bed, pillow, blanket, teddy bear,
plant, vase, mirror, clock, poster, whiteboard, trash bin, box,
suitcase, umbrella, bicycle, helmet, towel, sink, toothbrush, remote,
controller, television, refrigerator, microwave, kettle, pan, pot,
knife, fork, spoon, fruit, snack bag, water bottle, tissue box, key,
wallet, card, glasses case, watch, ring light, tripod, screwdriver,
tape, battery, light switch
