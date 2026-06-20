# SOMA — Market & Scope

**Compiled 2026-06-14 from three parallel research passes (market/competitive, EU legal/regulatory, technical feasibility & roadmap). Sources cited inline per section.**

> Product under evaluation (locked): an **input-only eyewear accessory** that converts real-world perception into structured **text on-device, in real time**, stores **zero raw media** (no video/audio/photo, ever), scales **detail by attention** (glance = gist, dwell = fine detail), and answers arbitrary **retroactive** questions from the text graph. North-star = **RAS** (Retroactive Answerability Score). This is NOT a recorder/lifelog and NOT an output/assistant device.

---

## 0. The one-paragraph verdict

The quadrant SOMA occupies — **physical-world visual input × no-raw-storage × persistent structured memory** — is **genuinely unoccupied** by any shipping product. The architecture's empirical quality (RAS +47.1, 0% hallucination on a 12-min home capture) **already exceeds published SOTA** on the closest academic benchmarks. The EU legal position is **defensible by design** (not a policy promise). The bet is real and the starting position is materially better than the pendant graveyard — but it rides on **one** existential risk that all three analyses independently surfaced: **you must be able to *prove* no raw media is retained.** Until that proof is hardware-credible, the strongest claim is also the most fragile.

---

## 1. Market & competitive landscape

**The white space is real.** No shipping product does continuous real-world *visual* perception that outputs only derived text. Classification of the field:

| Player | Input/Output | Modality | Storage | Form |
|---|---|---|---|---|
| Limitless (→Meta, Dec 2025) | Input | Audio | Raw audio→cloud | Pendant |
| Microsoft Recall | Input | Screen | Raw screenshots (local) | Software |
| Ray-Ban Meta Gen 2 | In+Out | Audio+on-demand cam | Raw media (Meta) | Glasses |
| Brilliant Labs Frame | In+Out | Camera+audio | Raw frames→cloud API | Glasses |
| Humane (dead Feb'25) / Rabbit | In+Out | Audio+cam | Cloud raw | Pin/handheld |
| Friend / Bee(→Amazon) / Plaud | Input | Audio only | Raw audio→cloud | Pendant |
| Mem0 / OmniQuery | Software | Digital | Derived text | API/app |
| Apple Vision Pro | Out | AR+cam | Raw spatial video | Headset |

Closest neighbor (Brilliant Frame) still ships raw frames to the cloud and keeps **no persistent memory graph**. The physical-world-visual × no-storage × memory cell is empty.

**Market size.** Smart glasses ≈ **$3–6B in 2026**, ~24% CAGR to ~$14B by 2033; **Ray-Ban Meta >7M units in 2025** (3× YoY) is the category anchor; Omdia projects ~10M units 2026. AI-memory software has no clean independent TAM (subsumed in "personal AI", ~$15–25B by 2030). Constructed SOMA SAM ≈ $0.6–1.2B by 2028 (EU premium + global knowledge workers, $300–500 device + $12–15/mo). All figures vary 2–5× across analysts.

**Graveyard post-mortem.** Failures = (1) phone-replacement framing, (2) server-bricking (Humane killed all units), (3) raw-media-in-cloud liability, (4) thin capture → hollow answers, (5) no delta over the phone. **SOMA avoids 3 of 5** by architecture (input-only/additive framing, local text graph survives offline, no raw media). **Shares 2**: battery/compute of always-on vision, social/bystander acceptability. **Adds 1 new one**: the privacy *credibility* gap (claim vs. provable).

**Business model & exit.** Hardware-at-cost + ~$12–15/mo subscription; break-even ≈ $25–30M ARR (~150k subs). No data-monetization path (the moat blocks it — a feature). Realistic acquirers: **Meta** (just bought Limitless for the audio layer; missing the *visual* layer), **Google** (Gemini glasses fall 2026, no memory graph), **Apple** (Vision Pro stalling, brand-aligned with privacy). Comparable acqui-hires $50–250M; a V2 with proven RAS + users is plausibly an $80–200M target.

*Sources: EssilorLuxottica earnings Feb'26 (CNBC); Meta/Limitless (AI Business); Omdia; Grand View Research; Humane/Rabbit post-mortems; Brilliant Labs; arXiv 2603.04930 (bystander privacy).*

---

## 2. EU legal & regulatory (Germany / Bavaria)

**§201 StGB (confidentiality of the spoken word): defensible by design.** The offense requires recording speech **onto a sound medium (Tonträger)**. A live transcription with no audio artifact is a **Live-Mitschrift**, long held *outside* §201; German commentary on AI transcription (2024–25) confirms brief RAM buffering immediately overwritten does not qualify. SOMA's live-STT-text-only maps squarely onto this — **the recording element is not met, provided implementation is genuinely zero-audio-write.** Residual: §201(2) Nr.2 (publishing speech "im Wortlaut") → **design rule: emit semantic facts/entities, never verbatim third-party quotes.**

**GDPR.** Household exemption is **lost outside the home** (Ryneš, C-212/13); the wearer is controller, lawful basis = legitimate interests (needs a documented LIA). **Art. 9 (biometrics) is avoided** by the **two-tier identity** design: Tier 1 = ephemeral text-only encounter sketches (soft descriptors, no template, auto-expire ~30d); Tier 2 = named person promoted **only** when the *human* links to a contact already lawfully held. No face/voice DB = the inverse of Clearview (which drew ~€90.5M in EU fines).

**EU AI Act.** The real-time biometric-ID prohibition is **law-enforcement-scoped** and needs a biometric template SOMA never builds → not prohibited, **not high-risk** under current Annex III (object/text recognition isn't listed). Transparency (Art. 50) is chatbot-scoped. But the Ray-Ban Meta precedent (DPC forced a bigger, blinking indicator; EU launch delayed) makes a **prominent always-on capture indicator the minimum social contract.**

**Load-bearing design rules:** zero audio write (any layer) · no verbatim third-party speech · no face/voice templates · on-device only · ephemeral + human-only promotion · visible indicator · no sensitive-attribute inferences · DPIA before commercial launch.

**Grants:** EXIST (TUM/Garching is a near-perfect fit; round active now) and EIC Accelerator (GenAI4EU / "Physical AI"; up to €2.5M) — winning narrative: *"architecturally incapable of surveillance — every regulatory red line is a structural impossibility, not a policy promise."*

**Needs a real lawyer (urgent first):** confirm no transient PCM disk-write by the OS audio stack; then LIA, DPIA, BayLDA pre-consultation on whether Tier-1 descriptors are "biometric," and bystander notice/erasure procedure.

*Sources: §201 StGB (gesetze-im-internet); unternehmensstrafrecht.de; EDPB Video Guidelines 3/2019; Ryneš; AI Act Art.5/Annex III; CNIL/Dutch DPA Clearview; EIC/EXIST.*

---

## 3. Technical feasibility & roadmap

**Academic ceilings (and why we're above them).**
- Ego4D NLQ temporal grounding: best ~**R@1 23%** (≤33% relaxed) — continuous-video grounding is structurally hard.
- EgoLife life-QA: frontier ~**36–46%** (EgoGraph 45.8%); easiest category is EntityLog (objects/space — *our* focus); **caption quality is the named bottleneck**.
- OmniQuery (closest system): **71.5%** on a human-rated scale (but uses intentional photos, not passive video).
- **EgoTextVQA (scene-text): frontier MLLMs ~33%, humans 27.7% indoor** — because they feed raw frames to an MLLM. **Our dedicated OCR channel is exactly the fix**, which is why caption-only (+17.6 / 36% halluc) → +OCR (+47.1 / 0% halluc). Our result already **exceeds published SOTA** on the analogous tasks.
- Hardest question types (all benchmarks): exact counting of look-alikes, tiny/oblique text, pattern-over-time, person re-ID, temporal grounding.

**On-device budget.** Cascade is mandatory:
- **Always-on (≈free):** Apple Vision OCR (`.fast`, ~frame-rate), on-device ASR (Neural Engine <1W; whisper.cpp ~15× real-time), pose (~1mW).
- **Event-triggered/sparse:** FastVLM-0.5B (~250ms TTFT → ~1 call/2–5s sustained), Moondream-2B, SmolVLM-256/500M as a scene-change pre-filter.
- **Hub-only:** Qwen2.5-VL-7B (~11s/frame — Mac/phone, not glasses).
- Phone-class all-day ≈ **1.7W active**; **heat throttles before battery** (sustained ~2W GPU throttles in minutes) → deep VLM calls **must** be novelty/dwell-gated. Glasses-class (~1 TOPS, <1W) → offload heavy compute to a pocket companion (the Orion pattern).

**Attention/salience scheduler (the core IP).** Dwell proxies today: ARKit head-pose velocity <5°/s for 500ms; object persistence across frames; scene-change cosine distance. On glasses: real gaze. Budget governor = per-60s thermal-scaled token budget; priority = 0.6·novelty + 0.4·dwell; long dwell → OCR + deep attribute pass; re-seen (low novelty) → skip (dedup). Novelty-vs-memory scoring is what makes detail follow attention.

**Object permanence / counting.** The 4-jars→2+2 error is the canonical IT3DEgo failure; the proven fix is **lifting tracks to 3D world coordinates via pose** (two objects at different world positions can't be the same instance). Honest ceiling: **~15–25% count error without dwell capture**; a "hold 2s on each" dwell protocol approaches 0%. The scheduler should *prompt* for a close look rather than silently guess.

**Roadmap (gates = RAS / hallucination):**
- **V1 software spine (now → ~4wk):** OCR on every flagged frame; SmolVLM scene-change pre-filter (cut VLM calls 3–5×); **3D world-coord dedup** (fix counting); budget governor (offline); expand battery to 30+ Qs. **Gate: RAS ≥ 60, halluc ≤ 5%.** *Riskiest assumption to de-risk FIRST: does OCR + refusal-default hold across 5 more rooms/lighting, not just the one tested?*
- **V2 live phone (4–12wk):** live dwell capture, FastVLM-0.5B event-gated + Qwen on hub, Gemma-2B incremental dedup, 2h no-throttle, founder cold test. **Gate: RAS ≥ 55 live, <3s dwell→memory.**
- **V3 eyewear (12–30wk):** gaze-based dwell, glasses+companion split, close the tiny-text gap, privacy-safe verifiable demo. **Gate: RAS ≥ 60, tiny-text ≥ 40%.**

**Top risks, attack order:** (1) hallucination generalizing beyond one room → test 5 rooms; (2) 3D dedup on reflective/clutter (kitchens, mirrors); (3) thermal throttle at 2h; (4) tiny/oblique OCR beyond ~20px chars; (5) glasses HW/SDK access (Aria $10k vs Ray-Ban bridge); (6) look-alike counting before first user test → ship the dwell-prompt.

*Sources: Ego4D/ObjectNLQ/OSGNet; NaQ; EgoLife/EgoGraph; OmniQuery; EgoTextVQA; IT3DEgo; EgoSeg3D; FastVLM; whisper.cpp.*

---

## 4. Synthesis — what to do with this

1. **The thesis survives scrutiny.** Empty market quadrant + above-SOTA quality + design-defensible EU legality. Don't re-run the "graveyard" doom analysis; it's the wrong comp set.
2. **The whole bet reduces to one provable claim:** no raw media retained. Make it *verifiable* (hardware kill switch / attestation / auditable firmware) — it is simultaneously the moat, the legal shield, and the existential risk.
3. **Next concrete lever (matches last night's finding):** 3D world-coord dedup + dwell capture to fix counting; then 5-room generalization test of OCR+refusal. That's the V1 gate to RAS ≥ 60.
4. **Fundable now:** EXIST (active round, TUM) on the EU-sovereign privacy-by-architecture narrative.
