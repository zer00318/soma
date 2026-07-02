# TRACE — TECHNICAL CHIEF SPRINT BRIEF
**Hard deadline: Wednesday 2026-07-01 (pitch). Today is Sat 2026-06-27. ~4 days. Full throttle.**

## YOUR ROLE
You are the **TECHNICAL CHIEF** for TRACE. The **Overall Chief (Claude)** holds the product nuance
and wrote the blueprint; the **founder (Satoshi)** pitches Wednesday. You OWN execution: architect,
build, integrate, verify. Move at maximum speed. **Conserve frontier/Codex tokens by pushing runtime
compute and bulk work to LOCAL LLMs** (ollama `gemma3:12b-it-qat` / `gemma3:27b-it-qat` at
`http://127.0.0.1:11434`). Verify everything yourself — self-tests are not proof; run it and read the
number.

## READ FIRST (the WHY — do not skip)
1. `ops/PRODUCT_TRUTH_SESSION_2026-06-27.md` — the decisions + the blueprint (PRIMARY, read fully).
2. `ops/PRODUCT_NORTH_STAR.md` — the product model.
3. `ops/ANTI_TUNNEL_LEASH.md` — failure modes to avoid.
Then THIS brief governs the sprint.

## THE GOAL (one sentence)
A pitchable **WOW demo** by Wednesday: founder's OWN space, **LIVE capture**, investors can ask
ANYTHING about that captured scene, answered from a **real cross-linked memory** with **shown
evidence** — and an honest **"I don't know"** wherever capture fell short.
**Bar: ≥75% answered, <10% confident-wrong. The <10% is NON-NEGOTIABLE — never trade it for coverage.**

## PRODUCT NUANCE (settled — do NOT re-architect)
- Continuous rich context: **vision = temporary-to-get-right, memory = permanent-to-compound.**
  Answers are RECONSTRUCTED from compounding cross-context memory, never read off a single frame.
- **The BRAIN (an LLM) decides** grouping / identity / relevance. NO hard-coded schemas or
  question-type routers. You build the SUBSTRATE + TOOLS; the brain reasons over them.
- **TWO MACHINES:** (1) deterministic SUBSTRATE (capture, cross-linked store, retrieval tools) —
  engineer + test hard; (2) nondeterministic REASONER (frontier-text LLM with tools) — prompt +
  MEASURE, never assert. Manage variance at the seam (precise retrieval + honest calibration).

## DEADLINE-ADJUSTED STRATEGY (important deviation from "greenfield")
The blueprint says greenfield. Under 4 days, **DO NOT delete the 100+ legacy scripts** — pure risk,
zero demo value. Instead: **build the missing SPINE as a new clean module and WIRE the working
capture + helpers into it as tools.** Defer all deletion/cleanup to post-pitch. Salvage aggressively.

## WHAT EXISTS + WORKS (salvage as tools — do NOT rebuild)
- **Capture:** `scripts/trace_brain_server.py` Mac-side perception (`TRACE_PERCEIVE=1
  TRACE_INSTANCE_PIPE=1`): GroundingDINO + per-crop gemma3 VLM + Vision OCR + pose/depth. Phone
  streams frames → Mac perceives → raw deleted. Force CPU for GroundingDINO where MPS asserts.
- **Helpers:** `scripts/instance_perceive.py`, `frame_quality.py` (blur gate), `perception_consensus.py`,
  `world_binder.py` (world-coordinate counting — validated on a real shelf), `scrub_pii.py`.
- **Persistence:** `src/trace_memory/adapters/sqlite_eventlog.py` (append-only log), `instance_graph.json`.
- **TEST DATA (use to prove the spine WITHOUT a fresh capture):**
  `data/phone_captures/_validated_shelf_20260627/` (25 real frames + depth + pose) and
  `data/phone_captures/live/ground_truth.json` (11 Q+A).

## WHAT TO BUILD (the spine — strict dependency order)

### 1. STORE — `src/trace_memory/store/` (the missing center of gravity — START HERE)
- Append-only typed observation log (reuse `sqlite_eventlog`): observation =
  {id, t, source, place, pose, text, provenance, embedding}.
- Cross-linked graph: entity nodes + edges {same_time, same_place, same_entity(semantic), succession}.
- Vector index for PRECISE semantic retrieval — use **local sentence-transformers** (ollama embed is
  broken on this box).
- Clean API: `write_observation()`, `link()`, `search(query,k)`→minimal sufficient slice,
  `neighbors(node)`→follow links, `get_abstractions()`.
- **Prove it:** ingest the 25 shelf frames → entities + links exist → `search` returns the right slice.

### 2. CAPTURE→STORE PATH
- Wire existing Mac perception output → `write_observation()` with provenance + pose. Don't
  over-engineer rate decoupling for the demo; reliability over fps.

### 3. SLEEP CONSOLIDATOR — `src/trace_memory/store/sleep.py` (LOCAL gemma)
- Dedup; author links (mechanical + semantic + a gemma "what groups/links here?" pass); write
  **FLAGGED abstractions** (marked derived, never mixed with observed). Reconsiderable; never harden
  weak links.

### 4. AGENTIC REASONER — `src/trace_memory/brain/agent.py` (THE WOW)
- Tool-using loop over the store. Tools: `search` / `neighbors` / `get_abstractions` / `read_observation`.
- **SELF-SCALING effort:** one cheap PRECISE pass first; escalate (more hops) ONLY when the model
  flags itself uncertain/contested. Do NOT over-reason easy questions ("where are my keys" = fast).
- Runtime model = **FRONTIER TEXT** (Claude/GPT via API, over DERIVED TEXT only — no raw media ever).
  Provide a **local-gemma fallback** for dev so you don't burn tokens while building/measuring.
- Output contract: `{answer, evidence_chain[citations], confidence, refused}`. Honest refusal at the
  edge of capture. Always show the work.

### 5. EVAL — `evaluation/annotate_live.py`
- annotate-as-you-live: founder appends `{question, true_answer, when}`. Score pass-rate over N
  reruns + confident-wrong rate. Gate ≥75% / <10%. **Run it against the shelf GT now for the first
  real number.**

## DELEGATE TO LOCAL LLMs (token discipline — founder is near limits)
- ALL perception, ALL sleep linking/abstraction, and DEV/EVAL-time reasoning run on **ollama
  gemma3:12b/27b**. Reserve frontier API for the FINAL demo reasoner only.
- Use the host **`.venv`** (transformers 4.49 / GroundingDINO / ultralytics / sentence-transformers).
  System python lacks numpy.
- Your sandbox has no ollama: emit worker scripts the founder/Overall Chief run on the host, or run
  via the host venv. Existing pattern: `scripts/local_model_worker.py`, `scripts/autonomous_worker.py`.

## GUARDRAILS (sacred)
- DO NOT tunnel into OCR — one tool of many; founder declared it closed.
- DO NOT fake the answer path — no cached-answer demo (dies on the first off-script question).
- Raw media deleted after perception; only derived text persists/egresses.
- The <10%-confident-wrong floor is the whole pitch; refusal is a FEATURE.
- Small, TESTED units. Verify by running. No new sprawl.

## DAY-BY-DAY
- **SAT/SUN:** Store (1) + capture→store (2), proven on the shelf capture. First eval number on shelf GT.
- **MON:** Sleep (3) + agentic reasoner (4) answering shelf questions with evidence + honest refusal.
- **TUE:** Wire frontier reasoner; founder captures the real DEMO scene(s) live; build the annotate
  set; measure + tune to the gate; identify the STRONG objects to stage around.
- **WED AM:** Rehearse the live flow end-to-end; lock it; verify honest refusal on out-of-scope Qs.

## REPORT
Append every milestone to `ops/SPRINT_HANDOFF.md` (what built, what VERIFIED with the actual number,
what's next, blockers). The Overall Chief reviews. Flag blockers immediately — do not silently stall.
