# Trace — Market & Positioning Research

**Purpose:** sourced figures to replace reasoned estimates in the KIT Gründerschmiede deck and to seed the EXIST‑Gründerstipendium application. Every number below carries a source or is labelled a stated assumption. Retrieved July 2026.

**Honesty rule for the deck:** if a number is a market-report headline, cite the firm. If it is a derived assumption (SOM, BOM, pricing), label it an assumption. Never present a modelled figure as a measured one — that is the same discipline the product is built on.

---

## 1. The competitive scoreboard (this is the strongest slide-8 material)

The "record‑everything" wearable category is simultaneously **booming and dying** — the two facts together *are* the problem statement.

- **Meta / EssilorLuxottica sold ~7 million AI glasses in 2025**, up from ~1M in 2024 and ~2M cumulative through 2023–24 — more than triple year‑over‑year. Source: [CNBC, Feb 2026](https://www.cnbc.com/2026/02/11/ray-ban-maker-essilorluxottica-triples-sales-of-meta-ai-glasses.html), [UploadVR](https://www.uploadvr.com/meta-essilorluxottica-sold-7-million-smart-glasses-in-2025/). → *Recording glasses are now a real, scaling consumer category.*
- **Humane's AI Pin is dead.** HP acquired Humane's assets for **~$116M** in Feb 2025 and shut the Pin's services (calls, messaging, AI queries, cloud) within weeks. Source: [TechCrunch, Feb 2025](https://techcrunch.com/2025/02/18/humanes-ai-pin-is-dead-as-hp-buys-startups-assets-for-116m/), [Axios](https://www.axios.com/2025/02/18/humane-ai-pin-shut-down-hp).
- **Rewind → Limitless was absorbed by Meta (Dec 2025) and the always‑on pendant wound down.** Rewind (always‑on screen+audio recorder) rebranded to Limitless in Apr 2024, pivoted to an AI pendant, then was acquired and folded into Meta's wearables push. Source: [Sacra](https://sacra.com/research/why-meta-bought-limitless/).

**Kill-shot line (sourced):** *"The two purpose-built always-on recorders of this generation — Humane's Pin and the Rewind/Limitless pendant — are already dead or absorbed. The category keeps failing at the retention wall. Trace removes the wall."*

Competitor positions for the 2×2 (physical-context × zero-retention):
- **Meta Ray‑Ban / AI glasses** — high physical context, **raw capture retained** (cloud). Bottom‑right.
- **Rewind / Limitless (defunct)** — high capture, high retention. Bottom‑right, now a headstone.
- **Apple Intelligence / Gemini** — high retention‑discipline on *digital* data, **blind to the physical world**. Top‑left.
- **Notion / PKM tools** — digital‑only, manual. Bottom‑left.
- **Trace** — physical context **+** zero retention. **Top‑right quadrant is empty; Trace is the first entrant.**

---

## 2. Market sizing (TAM / SAM / SOM)

### TAM — the AI smart‑glasses / wearable device market
- **Smart glasses hardware market ≈ USD 8.26 B by 2030** (Grand View Research). Source: [Grand View Research](https://www.grandviewresearch.com/press-release/global-smart-glasses-market).
- **IDC:** display‑less smart glasses ~10.6M units (2025) → **27.3M units by 2030** (~19% CAGR); category revenue ~$5.1B (2026); **installed base >80M smart glasses by 2030**. Source: [IDC](https://www.idc.com/promo/arvr/), [Next Reality summary](https://virtual.reality.news/news/smart-glasses-market-2026-growth-competitors-and-idc-forecasts/).
- Adjacent see‑through display glasses (XREAL/RayNeo/Viture) growing ~42% CAGR to 12.2M units by 2030 (IDC) — the wider wearable‑camera surface Trace's charm can attach to.

**Deck TAM figure:** **≈ €10 B by 2030** for the AI‑wearable device market (anchor: GVR $8.26B hardware + adjacent display‑glasses growth; ~€ at parity). Range €8–15 B depending on how much assistant‑integration revenue is counted. *Stated as a market‑report‑anchored range, not a point estimate.*

### SAM — EU / DACH, the GDPR‑filtered slice
- Europe is ~20–25% of the global consumer‑electronics wearable market; the EU over‑indexes on privacy willingness‑to‑pay.
- **Deck SAM figure: ≈ €2 B** (EU device market, privacy‑sensitive segment). *Assumption:* ~20% of TAM. The strategic point: **the harder the privacy law, the larger Trace's structural edge inside this slice** — competitors that retain raw data face rising compliance cost here; Trace faces none.

### SOM — DACH early adopters, 24 months post‑launch (bottom‑up)
- *Assumption chain:* ~**100k** reachable privacy/local‑AI enthusiasts in DACH × **15%** conversion × **€5/mo** (adoption‑priced membership) × 12 = **≈ €0.9 M ARR**.
- This is deliberately modest and consumer‑only. The consumer line is the **adoption/proof engine, not the profit engine** (see §4).

### Stage 2 — the real prize: the context layer for *all* AI
- **>2 billion smartphones already run local AI models** (on‑device SLMs). Source: [Edge AI & Vision Alliance](https://www.edge-ai-vision.com/2026/01/on-device-llms-in-2026-what-changed-what-matters-whats-next/).
- Voice/AI assistants number in the **billions of active endpoints** (Siri ~500M users; Siri + Google Assistant ~36% share each). Source: [SQ Magazine](https://sqmagazine.co.uk/voice-assistant-usage-statistics/).
- Every assistant (Siri, Gemini, ChatGPT) is racing toward *personalised* answers, which require the user's **physical** context — which none can capture without becoming a surveillance product.
- **Licensing‑layer TAM is best benchmarked by IP‑licensing comparables (§4): >€1B/yr per successful layer.**

---

## 3. Why now — three converging curves (all sourced)

1. **On‑device AI crossed the real‑time threshold.** Production object detection now runs sub‑20ms on mid‑range 2024–25 phones; Apple Intelligence runs a ~3B on‑device model; Gemma 3 spans 270M–27B; **>2B phones run local SLMs**. Trace was technically impossible ~24 months ago. Source: [AlephZero Labs](https://www.alephzerolabs.com/blog/on-device-ai-2026-sub-20ms/), [Edge AI & Vision Alliance](https://www.edge-ai-vision.com/2026/01/on-device-llms-in-2026-what-changed-what-matters-whats-next/).
2. **AI wearables ship in volume — and hit the privacy wall in public.** 7M glasses sold in 2025; simultaneously the pure recorders (Humane, Limitless) died/were absorbed (§1).
3. **EU AI Act enforcement has begun.** Prohibitions on **real‑time remote biometric identification** and **untargeted scraping of facial images** in force since **2 Feb 2025**; GPAI + governance obligations since **2 Aug 2025**; high‑risk (Annex III) obligations were set for 2 Aug 2026, deferred to **2 Dec 2027** under the Digital Omnibus provisional agreement (May 2026). "Structurally non‑retaining" becomes a procurement criterion, not a nice‑to‑have. Source: [European Commission](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai), [Trilateral Research timeline](https://trilateralresearch.com/responsible-ai/eu-ai-act-implementation-timeline-mapping-your-models-to-the-new-risk-tiers).

---

## 4. Business model — pricing, BOM, and the licensing precedent

### Hardware BOM (the charm)
- Trace's charm is **display‑less** — it clips to existing glasses and streams to the phone, which does all AI. This removes the single most expensive smart‑glasses component: in the Meta Ray‑Ban **Display** teardown, **display components are ~50.8% of total BOM** (TechInsights). Trace omits that entire category. Source: [TechInsights](https://www.techinsights.com/blog/meta-ray-ban-display-teardown-reveals-more-meets-eye).
- Remaining BOM = camera module (e.g. a Sony‑class image sensor as in Ray‑Ban), a BLE SoC, small battery + PMIC, housing. **Deck BOM figure: ≈ €15–25 at volume** (*stated assumption*, anchored by the display‑less teardown structure; first batches higher).

### Pricing philosophy (founder‑directed)
- **Consumer membership priced to spread: target €4–6/mo, charm included.** Consumer gross margin ≈ **0 by design** — the consumer line buys adoption and benchmark data, not profit.
- **Marginal compute cost ≈ €0** — inference runs on the customer's own phone. Trace can sustain adoption pricing indefinitely; cloud‑AI competitors structurally cannot (their marginal cost per query is real).
- **B2B licensing is the profit engine** (~100% software gross margin): license the zero‑retention physical‑context layer to eyewear/wearable makers and assistant platforms.

### Licensing precedent (sourced anchors)
- **Arm:** licenses CPU IP into billions of devices it does not manufacture; **licensing revenue ≈ $1.8 B in FY2025** (total revenue ~$4B). Source: [Arm FY2025 6‑K, SEC](https://www.sec.gov/Archives/edgar/data/0001973239/000197323925000010/exhibit992fye25q431-marx25.htm).
- **Dolby:** licenses audio IP into billions of devices it does not make; **licensing revenue ≈ $1.2–1.3 B/yr (FY2025)**. Source: [Dolby FY2025 results](https://www.prnewswire.com/news-releases/dolby-laboratories-reports-fourth-quarter-and-fiscal-year-2025-financial-results-302619023.html).
- **Deck line:** *"Arm doesn't sell chips and Dolby doesn't sell speakers — each earns >$1B/yr licensing a layer into devices they don't build. Trace doesn't need to profit on charms; it needs to become the context layer every device licenses."*

---

## 5. Slide‑2 "problem" evidence (replacing any unverifiable news quotes)

Use only verifiable facts:
- **Always‑on video is heavy and permanent.** Continuous 1080p H.264 at 4–6 Mbps = **~43–65 GB/day** (24h); ~2.5 GB/hr. A wearer's waking day (~16h) ≈ **~45–50 GB/day** of other people's faces, voices and screens — retained and searchable. Source: [security‑camera storage formulas](https://reolink.com/blog/cctv-storage-calculation-formula/). **Deck ledger figure: ≈ 50 GB/day** (*1080p, ~16 waking hours*).
- Recording wearables are scaling (7M/yr) *and* colliding with law (EU biometric/scraping bans, Feb 2025) and with commercial failure (Humane, Limitless). The dilemma is real and current.

---

## 6. EXIST‑Gründerstipendium facts (for slide 10 + application)

- **Monthly stipend by qualification:** student (≥½ studies done) €1,000; graduate w/ degree **€2,500**; PhD €3,000; +€150/child. Pranav (Master's student, holds a Bachelor's) → **€2,500/mo tier**.
- **Duration:** up to **12 months**.
- **Material costs:** up to **€10,000** (solo) / €30,000 (team); **coaching up to €5,000**; plus start‑up network access.
- Source: [BMWK/EXIST richtlinie](https://exist.de/wp-content/uploads/2025/02/Richtlinie-EGS-18-04-2023.pdf), [science‑startups.berlin](https://www.science-startups.berlin/programs/exist-startup-grant).
- **Team note:** EXIST favours teams of 2–3; Trace's team‑completion (the open Product/ML co‑founder seat) is framed as an explicit Horizon‑2 milestone the incubation coaching directly serves.

---

## 7. Net changes to make in the deck

| Slide | Was (estimate) | Now (sourced) |
|---|---|---|
| S2 ledger | "≈ 80 GB" | **≈ 50 GB/day** (1080p, ~16h) + source |
| S2 clips | fabricated news quotes | **real facts:** 7M glasses sold 2025; Humane Pin dead ($116M→HP); Limitless absorbed by Meta; EU biometric/scraping ban (Feb 2025) |
| S7 TAM | "€25–40B (IDC/Counterpoint)" | **≈ €10B by 2030** (GVR $8.26B + IDC installed base >80M) — honest range €8–15B |
| S7 SAM | "€5–8B" | **≈ €2B** EU/DACH privacy segment (assumption: ~20% TAM) |
| S7 SOM eq | "€9/mo" | **€5/mo** adoption price → ≈ €0.9M ARR (24 mo) |
| S7 platform | "~2B assistant users" | **>2B phones run local AI** (sourced) + billions of assistant endpoints |
| S7 why‑now | undated | **dated & sourced** EU AI Act (Feb 2025 / Aug 2025 / Dec 2027) |
| S8 | generic dots | + **sourced category‑death caption** (Humane, Limitless) |
| S9 BOM | "€15–25" bare | keep, **anchored** by Ray‑Ban display=50.8% BOM teardown (Trace omits display) |
| S9 precedent | Arm/Dolby named | **numbers:** Arm ~$1.8B, Dolby ~$1.2–1.3B licensing/yr |
