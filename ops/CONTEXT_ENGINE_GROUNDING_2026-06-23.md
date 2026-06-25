# Context Engine — Phase 1 Grounding (2026-06-23)

*Verified substrate for the HELPERS→INJECTION→LLM blueprint: what the repo really is,
the IPP-poster worked example with the truth of `089 289 112` established by primary sources,
and the current-2026 on-device tech envelope. Produced by the Phase-1 workflow grounding agents;
kept so the blueprint stays buildable, not astronomy.*

---

## A. Repo reality — HELPERS exist; INJECTION is concatenation; web-expansion + premise-check are ABSENT

I now have a complete, grounded picture. Here is the blueprint grounding.

---

# TRACE engine — what ACTUALLY exists vs. the HELPERS→INJECTION→LLM thesis

Repo root: `/Users/zer00/Documents/VLM`. Verdict up front: the **HELPERS** layer is real and diverse; the **INJECTION** layer exists as *dossier concatenation + ranking + a deterministic grounding gate* but does **no entity fusion-into-facts, no web/knowledge expansion, and no premise-check**; the **LLM stand-your-ground** behavior is *prompt-asserted but not enforced* — refusal is enforced structurally, not premise-falsification. There is **zero web/knowledge-lookup code anywhere in the repo**.

## 1) HELPERS that exist today

| Helper | Modality | Emits | Where (file:line) | On-device / Mac |
|---|---|---|---|---|
| gemma3 VLM perceiver | vision→text | SCENE / OBJECTS / TEXT / PEOPLE per frame | `scripts/trace_live_feed.py:40` (`PERCEIVE_PROMPT`), `:184` (`perceive`) | Mac (Ollama) |
| Apple Vision OCR | vision→verbatim text | OCR lines, in-memory, authoritative over VLM TEXT | `scripts/trace_live_feed.py:108`, `merge_ocr` `:113`; native `ContentView.swift:1397/1584` (VNRecognizedText) | both (Mac via `evaluation/vision_ocr`, device via Vision) |
| Apple Speech (on-device) | audio→text | live transcript, committed segments | `TraceLiveContextEngines.swift:15` (`SFSpeechRecognizer`, `requiresOnDeviceRecognition=true` `:240`) | device |
| whisper.cpp stream | audio→text | streaming ASR (macOS fallback path) | `TraceLiveContextEngines.swift:56` (`startWhisperStreamIfAvailable`) | Mac |
| CoreLocation + reverse-geocode | GPS→place name | `locationMemoryHint` "GPS lat,lon \| Place, City, Country" | `TraceLiveContextEngines.swift:337`, geocode `:391` | device |
| Detector + track salience | vision | per-track class, `seen_count`, motion | `TraceDetectorBridge.swift:211` (`seen_count>=3` gate); scheduler `EnrichmentScheduler.swift:50` (`SalienceScorer`) | device |
| Audio-event analyzer (build-time) | audio→events | energy/pitch events log, NOT speech | `scripts/ask_home.py:1086` reads `audio_events.json`; built once by `build_audio_events.py` | Mac (capture-time) |

Confidence is real per-helper: OCR refuses (TEXT: NONE) rather than guess (`merge_ocr` `:120`); detector requires `seen_count>=3`; whisper lines are noise-filtered (`cleanWhisperTranscript` `:153`).

## 2) The INJECTION / assembly layer — and its exact limits

The "injection" today is `answer_assembler` → `gather_evidence` → `build_evidence_dossier` (`ask_home.py:2698`, `:1389`, `:1510`).

What it **does**:
- **Gathers** every text channel beside the memory into one dict (`gather_evidence:1389`): kf OCR+caption, `micro_details`, world inventory, transcript, `audio_events`, `screen_memory`, episodes, `attributes`, `bound_memory`, `entity_capture`.
- **Ranks per channel** by question-keyword overlap + semantic (`bge-m3`) union + a distinctive-token FOCUS bonus (`build_evidence_dossier:1510`, `_kf_rank:1571`, `ASSEMBLER_KF_SEM_UNION:1296`).
- **Tags every line** with `source + timestamp`, caps per channel (`ASSEMBLER_MAX_PER_CHANNEL=10`), emits one delimited dossier string (`:1586`).
- **Cross-frame OCR consensus** is a real fusion primitive: `consensus_recall.consensus_read` (`consensus_recall.py:108`) folds truncated reads into complete ones (substring clustering `:152`), frequency=vote-weight (`tally[k]+=mult :144`), refuses below quorum. **But it is only invoked on the *anchored* live read path** (`ask_home.py:2750`), NOT inside the dossier assembler.
- **Deterministic structured slots** (`structured_recall.py:475`): identity/outfit/institution/labeled-IDs/poster-count/occupancy, each requiring `MIN_REPEAT_SUPPORT>=2` cross-observation corroboration with attached provenance — this is the closest thing to "fuse into typed facts," and it **is** frequency=confidence.
- **Native digest** pre-fuses on device into `stable / provisional / stale-but-remembered` facts keyed by `observations` count (`ContentView.swift:2274`, `updateContextFacts:1195` increments `observations`), with seen-count thresholds (`>=3` = stable).

**Limits (the gap to the thesis' INJECTION):**
- **(a) Fuse cross-helper outputs into entities/facts:** PARTIAL. Done only by `structured_recall` slots and `entity_capture`/`bound_memory` *if those files were pre-built offline*; the live assembler dossier is **flattened per-channel lines**, not unified entities. `entity_graph.binding_confidence` exists but is used only as a *refusal gate*, not to build the evidence packet.
- **(b) Resolve identity:** PARTIAL — `self_entity`, `entity_graph` cluster typed entities, but only consumed by the gate (G1), not folded into the answer packet.
- **(c) EXPAND live via web/knowledge lookup:** **ABSENT.** Repo-wide grep for `WebSearch/requests.get/httpx/wikidata/wikipedia/reverse-lookup` → **zero hits** in `scripts/` and `src/`. The only "world knowledge" allowed is the LLM normalizing capitalization of a name *already in the text* (`ASSEMBLER_PROMPT:2229`). A phone-number→institution expansion does not exist.
- **(d) Corroborate across helpers (frequency=confidence):** PARTIAL — real in `consensus_recall` and `structured_recall` (repeat thresholds) and the native digest seen-counts; NOT in the main dossier (it ranks, doesn't vote).
- **(e) Rich grounded evidence packet:** it's a **tagged text dossier string**, not a structured packet of entities+facts+confidences.
- **(f) Check the user's premise:** **ABSENT** in the engine. The only premise/trap awareness lives in the *eval harness* (`scripts/ask_live.py:30` "adversarial false-premise / trap bank") — there is no `premise`/`refute`/`contradict` logic in `ask_home.py`.

## 3) Honesty / refusal mechanism today (what makes it refuse vs lie)

Refusal is **deterministic and structural**, not LLM-judgment (the prompt-refusal approach was abandoned — see `:2273`, "prompt-tuning the refusal rule is dead"):

- `structural_grounding(question, draft, memory_path)` (`ask_home.py:2561`), returns `assert | refuse | ambiguous`:
  - **G1 binding ambiguity** (`:2581`): specific-item question + ≥2 competing entities → `AMBIGUOUS_REFUSAL` (via `entity_graph.binding_confidence`).
  - **G2 verbatim-value** (`:2619`): a clock time / brand / state word asserted must appear literally in `_raw_text_corpus`; else refuse. State words additionally must be `_state_bound_to_question_entity`.
  - **G3 phantom-presence floor** (`:2648`): a caption-only presence claim below `ASSEMBLER_CONF_MIN=0.6` (`presence_confidence`) → refuse; negations/faint-attributes exempt.
  - **G4** corpus-grounding floor exists but is **DISABLED** (`ASSEMBLER_G4_FLOOR=False:2417`, proven a net regression).
- Consensus path (`consensus_read:108`): below-quorum reads return `NOT IN MEMORY`; the anchored live read path **refuses rather than falling through to the fabrication-prone assembler** (`ask_home.py:2761-2767`).
- Per-channel honest refusals: OCR `TEXT: NONE`, audio "no usable speech" (`:1146`), spatial "no pose/heading stored" (`SPATIAL_REFUSAL:969`).
- The gate is **conservative/non-regressing**: any missing module → `assert` pass-through; it only ever DEMOTES, never invents.

What this is **not**: it is *grounding-in-captured-text*, not *premise-falsification*. The LLM does not say "your question is wrong because X"; it either answers from the dossier or emits the canned `GROUNDED_REFUSAL`/`AMBIGUOUS_REFUSAL`. The COMMIT prompt (`:2282`) actively biases the LLM toward answering, with the structural gate as the only safety net.

## 4) Storage / state today

- **Brain query-time:** plain JSON files in a memory dir — `kf_memory.json` (keyframe list: `{t, frame, caption, ocr[]}`), `world_memory.json` (`{objects:[...]}`), plus sibling `micro_details / screen_memory / audio_events / transcript|asr / attributes / bound_memory / entity_capture / entity_centric / episodes`. Resolution: `_resolve_memories:128`. **No raw media at query time** (`load_audio_events:186` reads cached text log, never the wav).
- **Hexagonal core (`src/trace_memory/`):** mostly *scaffolding/ports*, not yet load-bearing. Domain models are real (`Observation` with typed `Attribute`/`Confidence`/`Provenance`, `observation.py:19`); `adapters/sqlite_eventlog.py` (102 lines) is the only substantive store adapter; `application/recall.py:7` is a strangler wrapper delegating to `legacy_ask_home.py:19` which just calls `ask_home.ask`. `application/grounding_gate.py` is a **1-line stub** ("enters in Phase 3"). Most ports/adapters are 1-line placeholders.
- **Native device:** append-only NDJSON log (`appendNativePayload:2327`) of `native_context_digest` records; in-memory `contextFacts` dict with `observations` counts, stable/provisional/stale tiers (`:2274`).

## 5) Biggest GAPS to a HELPERS→INJECTION→LLM engine with live web-expansion + stand-your-ground LLM

1. **INJECTION is concatenation, not fusion.** No component takes the N helper outputs and emits a unified set of typed entities/facts with merged confidences as *the* answer substrate. `entity_graph`/`self_entity` exist but feed only the *refusal gate*. **Build:** a real fusion stage that turns ranked channel lines into `Observation`/`Entity` objects (the `src/trace_memory/domain` types already exist) → a structured evidence packet, replacing the dossier string. The consensus primitive (`consensus_recall.py`) and structured slots (`structured_recall.py`) are the seeds; they need to run *inside* assembly, not as side paths.

2. **No live web/knowledge expansion at all.** This is the thesis' single most novel claimed layer and it is **entirely absent** (grep-confirmed). **Build:** an `Expander` port that takes a fused fact (a read phone number, an institution name, a station sign, a product logo) and enriches it via web/knowledge lookup, attaching the result as new corroborating observations with their own provenance/confidence. Nothing in the repo does I/O to the network for enrichment. Deferred tools `WebSearch`/`WebFetch` are available to the agent but unused by the engine.

3. **No premise-check / stand-your-ground.** The engine answers-or-refuses; it never *contradicts a false premise* ("there was no train — that's a mural"). False-premise handling exists only in the eval trap bank (`ask_live.py:30`), not the answer path. **Build:** a premise-verification step before phrasing — given the fused packet, detect when the question presupposes a fact the evidence refutes, and have the LLM assert the contradiction rather than pivot. Today G1/G2/G3 produce a *silent canned refusal*, which is honest but not "stands its ground."

4. **Consensus/corroboration is wired only on the anchored live read path, not the default brain.** `consensus_read` is invoked only when `anchor is not None and kind in (reading,screen)` (`ask_home.py:2750`); the resume memory note confirms it is "not yet wired into ask_home" generally. **Build:** make frequency-consensus the assembler's default fusion mechanic across all channels, not just OCR-at-an-anchor.

5. **Hexagonal core is scaffolding.** The clean `domain/ports/adapters` that a real engine should be built on is ~90% 1-line stubs (`grounding_gate.py`, most ports); the live system is the monolith `scripts/ask_home.py` (2924 lines). The blueprint's "honesty moat / typed observations with refutation cues" maps directly onto `Observation.refutation_cue` (`observation.py:30`) — which is **defined but never produced or consumed**. **Build:** migrate the working `ask_home` logic behind the ports so fusion/expansion/premise-check are composable stages, and actually populate `refutation_cue` so the stand-your-ground LLM has refutation signals to stand on.

Key files: `scripts/ask_home.py` (assembler `:2698`, gate `:2561`, ask seam `:2733`), `scripts/consensus_recall.py:108`, `scripts/structured_recall.py:475`, `scripts/trace_live_feed.py` (helpers+OCR merge), `trace-native-fastvlm/FastVLM App/TraceLiveContextEngines.swift` (device speech/location), `EnrichmentScheduler.swift` (salience budget), `ContentView.swift:1195/2269` (digest+seen-counts), `src/trace_memory/domain/observation.py:19`.

---

## B. Worked example — the IPP poster, truth verified (089 289 112)

I have enough verified facts. The truth is clear and confirmed by primary sources. I'll model the pipeline now.

The critical reconciliation: the founder's "TUM's emergency hotline" label is **partly wrong but landing on a real truth**. 089 289 112 IS dialed into TUM's exchange (089 289 = TUM switchboard), operated by TUM's Werkfeuerwehr — but it serves the *entire shared Forschungscampus Garching*, IPP included. IPP's own exchange is 089 3299, not 289. So the poster (Max-Planck letterhead) routes its campus emergency through TUM's plant fire brigade.

---

## TASK A — Established truth (cited)

**1. Is 112 the German/EU emergency number?** Yes. 112 is the single Europe-wide emergency number, introduced 29 July 1991, free and dialable without prefix in all EU states; in Germany it reaches fire + rescue (110 is police). The poster's center panel ("Notruf 112 / Feuer, Erste Hilfe… jederzeit erreichbar") is correct. ([European Commission FAQ](https://ec.europa.eu/commission/presscorner/detail/en/memo_08_358); [Offenbach Feuerwehr](https://www.offenbach.de/microsite/feuerwehr/historie/feuerwehr-notruf112.php?loc=en); [Lingoda 110 vs 112](https://www.lingoda.com/blog/en/emergency-calls-in-germany/))

**2. Whose exchange is "089 289"?** TUM's. `089` = Munich area code; `289` = TUM's central PBX exchange (main switchboard +49 89 289 01, used across all TUM Munich/Garching sites). ([TUM Contact](https://www.tum.de/en/about-tum/contact-directions); [TUM CIT contact](https://www.cit.tum.de/en/cit/school/contact/))

**3. What is 089 289 112 actually?** It is the **direct emergency line of the TUM Werkfeuerwehr (plant fire brigade) on the Garching research campus**, the recommended number to dial *from a mobile* (a mobile 112 hits the public Munich control center, not the on-campus brigade). The brigade sits at Römerhofweg 67, Garching, non-emergency line 089 289 12024. ([Werkfeuerwehr Garching – Kontakt](https://www.hr6.tum.de/feuerwehr/kontakt/); [Stadt Garching – TUM Feuerwehr](https://www.garching.de/Hochschul_+und+Forschungszentrum/Technische+Universit%C3%A4t+M%C3%BCnchen+%28TUM%29/TUM+Feuerwehr.html))

**4. Reconcile the IPP-vs-TUM contradiction (the honest part):**
- The poster letterhead is genuinely **Max-Planck-Institut für Plasmaphysik (IPP)** — and IPP's *own* phone exchange is **089 3299** (main +49 89 3299-01), **not** 289. ([IPP Imprint](https://www.ipp.mpg.de/2345/imprint))
- So 089 289 112 is **not IPP's own number**. It belongs to TUM's exchange and TUM's fire brigade.
- The resolution: IPP shares the **Forschungscampus Garching** with TUM, and the TUM Werkfeuerwehr is the **plant fire brigade for the whole shared campus**, so an IPP safety poster correctly points occupants to the TUM brigade's on-campus emergency line. ([Brandschutz-Richtlinie Forschungscampus Garching, TUM HR6](https://www.hr6.tum.de/feuerwehr/kontakt/); [IPP Garching site / Boltzmannstraße 2](https://www.ipp.mpg.de/17301/garching))

**Verdict on the founder's label:** "TUM's emergency hotline" is **the operator-correct half and the institution-wrong half**. The *number/brigade* is TUM's (089 289 exchange, TUM Werkfeuerwehr) — so calling it "TUM's" is defensible. But it is **not** "*the* emergency number of TUM-the-university" generically and it is **not IPP's own**; it is the **shared-campus plant-fire-brigade line** that an IPP building uses by virtue of campus geography. The honest one-liner: *"089 289 112 = the TUM Garching plant fire brigade's direct mobile-emergency line, which also serves IPP because they share the Garching research campus; IPP's own switchboard is 089 3299."*

---

## TASK B — Pipeline model for THIS image

### (1) HELPERS — parallel, diverse, redundant; each typed + confident; honest channels refuse

| Helper | Plausible raw output (typed observation + confidence) |
|---|---|
| **OCR-A (dense text)** | `text_block{region:center, "Notruf 112 / Feuer, Erste Hilfe und technische Notrufe / Der Notruf ist jederzeit erreichbar", conf 0.96}`; `text_block{region:top-left,"Sirenenalarm / Feueralarm", 0.94}`; `text_block{"Bei Ertönen des Gebäudealarms Gebäude verlassen und zum Sammelplatz gehen!", 0.9}`; `text_block{"Alarm-Meldung Notruf Nr.:112 / Wer meldet? / Was ist geschehen? / Wo ist es passiert?", 0.92}` |
| **OCR-B (table/form parser)** | `kv_table{header:"Abteilung", rows:[{Zentrale Sicherheit:1314},{Leiter Zentrale Sicherheit:1364},{Arbeitssicherheit:1220},{Strahlenschutz:1364},{Brandschutz:1145},{Objektschutz:1145},{Hauptpforte:1401},{Umweltschutz:1827},{Abfallbeauftragter:1665},{Betriebsarzt:1410}], conf 0.82}` — flags these are **extensions** (3–4 digits), not full numbers |
| **OCR-C (handwriting channel, separate model)** | `handwritten_text{"089 289 112", style:marker, conf 0.78}` — lower confidence, flagged distinct from print |
| **Object/attribute namer** | `object{type:"handwritten number", attribute:"boxed in black marker", salience:high, conf 0.85}`; `object{type:"safety poster", conf 0.9}` — the *attribute that it's emphasized by a human* is itself an observation |
| **VLM scene captioner** | `scene{"laminated safety/evacuation poster mounted on an indoor wall; institutional building", conf 0.83}` |
| **Logo / letterhead recognizer** | `entity_candidate{"IPP — Max-Planck-Institut für Plasmaphysik", source:letterhead+logo, conf 0.8}`; `text{"IPP Survey 3.2014"}`; `text{"Sicherheitsinformation"}` |
| **Language ID** | `lang{de, conf 0.99}` → tells injection to translate/normalize for an English-asking user |
| **Layout/region segmenter** | `layout{yellow-header bands, blue "WER? WAS? WO?", center red/white 112 block, right-edge branding column}` — gives every text block a spatial role |
| **Spatial/pose channel** | `spatial{poster on wall, upper-right of frame, ~1.5m, fronto-parallel}` — supports "where am I / what am I looking at" |
| **Honest refusal stance (all channels)** | No channel emits a `wifi`, `password`, `SSID`, or `personal-name` observation, because none is present. This silence is load-bearing: the absence is what lets the system refuse the false premise instead of confabulating. |

### (2) INJECTION — fuse + expand + corroborate → grounded evidence packet

**(a) Fuse cross-helper outputs into entities/facts.** Merge OCR-A "Notruf 112" + form-parser "Notruf Nr.:112" + scene "evacuation poster" → fact `EMERGENCY_NUMBER = 112 (Feuer/Erste Hilfe/technische Notrufe, immer erreichbar)`. Merge letterhead recognizer + "IPP Survey 3.2014" → entity `PLACE = IPP, Max-Planck-Institut für Plasmaphysik`.

**(b) Resolve identity.** The handwritten `089 289 112` is bound as a *distinct, human-emphasized* fact, NOT collapsed into the printed "112". Identity note: this is a **fuller-form number containing 112**, marker-boxed → high human salience, treat as a deliberately-added local instruction.

**(c) EXPAND live via web/knowledge lookup (the novel step).** Injection issues lookups:
- `089` → Munich area code. ✔
- `089 289` → **TUM central exchange** (switchboard 089 289 01). ([TUM](https://www.tum.de/en/about-tum/contact-directions))
- `089 289 112` → **TUM Werkfeuerwehr Garching, mobile-emergency direct line**; non-emergency 089 289 12024. ([Werkfeuerwehr Garching](https://www.hr6.tum.de/feuerwehr/kontakt/))
- `IPP` → Max-Planck-Institut für Plasmaphysik, **Boltzmannstraße 2, 85748 Garching**, own exchange **089 3299**. ([IPP Imprint](https://www.ipp.mpg.de/2345/imprint))
- `112` → EU-wide emergency number, free, no prefix. ([EC FAQ](https://ec.europa.eu/commission/presscorner/detail/en/memo_08_358))

**(d) Corroborate / detect the cross-source conflict.** Injection now holds two place-signals: letterhead says **IPP (089 3299)**, handwritten number resolves to **TUM exchange (089 289)**. Rather than averaging or guessing, injection records the *reconciliation fact*: **shared Forschungscampus Garching → TUM Werkfeuerwehr is the plant fire brigade serving IPP too.** Frequency/agreement: "112 as the call-this number" is corroborated by 3 independent helpers (OCR-A, form-parser, EU lookup) → high confidence; "this place = IPP" corroborated by letterhead+survey-tag → high; "089 289 112 = TUM campus brigade" corroborated by web lookup → high but flagged as cross-institution.

**(e) Premise pre-checks staged:** `wifi/password = NULL (no channel emitted)`; `numbers present = {112, 089 289 112, extensions 1314/1364/1220/1145/1401/1827/1665/1410/1220, IPP-main 089 3299}` — all are *emergency/safety/switchboard*, none is a credential.

**Resulting evidence packet (sketch):**
```
PLACE: IPP – Max-Planck-Institut für Plasmaphysik, Garching research campus
       (Boltzmannstraße 2, 85748). Confidence 0.86 (letterhead+survey-tag).
EMERGENCY_PRIMARY: 112 — EU emergency (fire/first-aid/technical), always reachable. Conf 0.95.
EMERGENCY_LOCAL: 089 289 112 — handwritten/boxed; resolves to TUM Werkfeuerwehr Garching
       direct line (089 289 = TUM exchange). Best to dial from a mobile on campus. Conf 0.8,
       flagged: TUM-operated, serves IPP via shared campus.
INSTITUTION_NOTE: 089 289 = TUM exchange ≠ IPP's own 089 3299. Reconciled: shared campus.
SAFETY_PROTOCOL: on building alarm, leave building → assembly point; follow Einsatzleiter
       Feuerwehr / Leiter Zentrale Sicherheit; report Wer/Was/Wo.
INTERNAL_EXTENSIONS: Zentrale Sicherheit 1314, Leiter 1364, Brandschutz/Objektschutz 1145,
       Hauptpforte 1401, Betriebsarzt 1410 … (3–4 digit = in-house extensions, not dialable
       externally without 089 3299 prefix). Conf 0.8.
LANG: source German; user-facing answer normalized to query language.
ABSENT_CHANNELS: wifi=∅, password/SSID=∅, person-name=∅.  ← refusal basis
```

### (3) LLM answers — grounded only in the packet

**Query 1 (correct): "What number do I call in an emergency here?"**
> **Call 112** — the EU emergency number for fire, first aid and technical emergencies, free and always reachable. You're on the Garching research campus (IPP), and someone has hand-written a direct campus line, **089 289 112**, on this poster — that reaches the **TUM plant fire brigade (Werkfeuerwehr) that covers this campus**, and it's the better number to dial *from a mobile* so you reach the on-campus brigade rather than the city control center. On an internal house phone you can also reach Zentrale Sicherheit at extension **1314**. *(grounded: EMERGENCY_PRIMARY, EMERGENCY_LOCAL, extensions; cited [112-EC], [Werkfeuerwehr])*

**Query 2 (recall): "Whose building is this / where am I?"**
> You're at the **Max-Planck-Institut für Plasmaphysik (IPP)** on the **Garching research campus** near Munich (Boltzmannstraße 2). One honest nuance: the hand-written emergency line on the poster, 089 289 112, is on **TUM's** exchange, not IPP's own (IPP's switchboard is 089 3299) — that's because **TUM's fire brigade serves the whole shared campus**, IPP included. So: *IPP's building, TUM's campus fire brigade.* *(grounded: PLACE, INSTITUTION_NOTE; this is exactly the conflict injection reconciled rather than smoothing over)*

**Query 3 (FALSE PREMISE — stand its ground): "What's the wifi password on this poster?"**
> There is **no wifi password on this poster**, and I won't invent one. This is an **IPP safety/evacuation poster** — its content is emergency numbers (112; the campus fire line 089 289 112), the evacuation/assembly-point protocol, and a table of internal safety **extensions** (Zentrale Sicherheit 1314, Brandschutz 1145, Betriebsarzt 1410, …). I'm flagging your premise as wrong rather than guessing: none of my reading channels detected an SSID or credential, and I won't repurpose those extension digits as a "password." *(grounded: ABSENT_CHANNELS=∅ for wifi/password; the refusal **names the missing channel** — the honesty moat. It does NOT pivot to a plausible-looking number from the table.)*

---

**Files / artifacts relevant:** none written (analysis only, per instructions). Verified primary sources are the IPP imprint (089 3299), the TUM Werkfeuerwehr Garching contact page (089 289 112 / 089 289 12024), the TUM switchboard (089 289 01), and the EC 112 FAQ — all linked inline above.

---

## C. Current-tech envelope (2025–2026), real numbers + citations

I have enough grounded data across all six building blocks. Assembling the final report.

# On-Device Continuous Context Engine — Capability Scan (2025–2026)

Real numbers, sourced. Maturity = SHIP TODAY / NEAR / ASPIRATIONAL. Where a vendor only published relative speedups (Apple FastVLM is the worst offender), I flag it rather than inventing absolutes.

## 1. On-device VLM (the bottleneck)

| Option | Real numbers | Device | Maturity | Source |
|---|---|---|---|---|
| **Apple FastVLM 0.5B / 1.5B / 7B** | 85× faster TTFT vs LLaVA-OneVision-0.5B; 5.2× vs SmolVLM; 21× vs Cambrian (7B). Vision encoder emits 4× fewer tokens than FastViT, 16× fewer than ViT-L/14 @336px. **Apple publishes NO absolute ms or tok/s.** Demo ran "near real-time" on iPhone 16 Pro. Int8 + WebGPU builds open-sourced. | iPhone 16 Pro | **SHIP-ish** (weights public, but you must benchmark absolutes yourself) | [Apple ML Research](https://machinelearning.apple.com/research/fast-vision-language-models), [HF int8](https://huggingface.co/apple/FastVLM-1.5B-int8) |
| **moondream2 (2B, 4-bit)** | TTFT **3.8–4.0 s** on **iPhone 14** (16-bit 4.008 s → 4-bit 3.914 s). Avg **<5 tokens/s** decode (MobileAIBench). Robust to 3-bit quant. | iPhone 14 | NEAR (too slow for live; fine for async/brain) | [MobileAIBench arXiv](https://arxiv.org/html/2406.10290v1), [HF 4bit](https://huggingface.co/moondream/moondream-2b-2025-04-14-4bit) |
| **Qwen2.5-VL via MLX-VLM (3B/7B)** | MLX ≈ **2× tok/s** over PyTorch/GGUF on identical HW. M-series reference: Gemma-class ~158 tok/s on M5 Max (text). No published iPhone VLM tok/s. | M-series Mac (not iPhone-validated) | SHIP on Mac / ASPIRATIONAL on iPhone | [LLMCheck](https://llmcheck.net/benchmarks), [MLX-VLM perf blog](https://blog.pebblous.ai/blog/mlx-vlm-physical-ai-edge/en/) |

**Verdict:** No on-device VLM does true real-time (≥10 fps) captioning on iPhone today. Best honest path = FastVLM-0.5B for fast TTFT on key frames + heavy lifting async in a "brain." Sub-5 tok/s decode is the hard wall — matches your existing finding that live = bounded helpers, brain = unbounded.

## 2. On-device OCR (your validated text core — this is the strongest cell)

| Option | Real numbers | Device | Maturity | Source |
|---|---|---|---|---|
| **Google ML Kit Text Recognition v2** | **~0.05 s/image** (6× faster than Apple Vision accurate). Latin-only in base model. | iPhone 12 | **SHIP TODAY** | [bitfactory comparison](https://www.bitfactory.io/de/dev-blog/comparing-on-device-ocr-frameworks-apple-vision-and-google-mlkit/), [ML Kit docs](https://developers.google.com/ml-kit/vision/text-recognition/v2/ios) |
| **Apple Vision `VNRecognizeText` (accurate)** | **~0.31 s/image**; fast mode much quicker but "underwhelming" quality. Per-word confidence, custom-word hints, language correction, simplified Chinese support ML Kit lacks. Both held accuracy to ~20° rotation; Vision better past that. | iPhone 12 | **SHIP TODAY** | [bitfactory](https://www.bitfactory.io/de/dev-blog/comparing-on-device-ocr-frameworks-apple-vision-and-google-mlkit/) |

**Verdict:** Fully shippable now. Both run in-memory, no network, 0-raw-media-retained by construction. ML Kit wins raw latency 6:1; Apple Vision wins features (confidence values — directly useful for your consensus-recall frequency=confidence scheme). This is your most mature building block and it's exactly where your validated 47%→60% text-recall win lives.

## 3. On-device ASR

| Option | Real numbers | Device | Maturity | Source |
|---|---|---|---|---|
| **WhisperKit (large-v3 turbo, Core ML/ANE)** | **2.2% WER** (best in class), **~0.46 s** mean latency — matches gpt-4o-transcribe/Deepgram nova-3 server-side. Sub-100 ms streaming on iPhone 15 Pro. ANE stateful decoder: 8.4→4.6 ms/forward-pass (−45%) on M3. | iPhone 13+/15 Pro, M3 | **SHIP TODAY** | [WhisperKit arXiv 2507.10860](https://arxiv.org/abs/2507.10860), [Soniqo benchmarks](https://soniqo.audio/benchmarks) |
| **Apple SpeechAnalyzer (iOS 26)** | ~**2× faster than Whisper Large-v3 Turbo**; most accurate on read-aloud FR/ES/DE/IT (Italian 4.0% WER); WhisperKit still edges EN/ES. No 1-min cap, long-form, auto language detect. | iOS 26 device | **SHIP TODAY** (iOS 26+ only) | [MacRumors](https://www.macrumors.com/2025/06/18/apple-transcription-api-faster-than-whisper/), [Argmax](https://www.argmaxinc.com/blog/apple-and-argmax) |

**Verdict:** Fully shippable. SpeechAnalyzer is the zero-dependency default on iOS 26; WhisperKit if you need max accuracy / noisy / accented audio / older OS. Both real-time at <0.5 s.

## 4. On-device embeddings + vector store

| Option | Real numbers | Maturity | Source |
|---|---|---|---|
| **all-MiniLM-L6-v2 (22M, 384-dim) via Core ML** | ~14k sentences/s on desktop CPU; Core ML on A17 Pro/iPhone 15 Pro → low-tens-of-ms inference, int8-int8 ANE throughput boost. 5× smaller than BERT-base. | **SHIP TODAY** | [HF MiniLM](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [coremltools perf](https://apple.github.io/coremltools/docs-guides/source/opt-quantization-perf.html) |
| **sqlite-vec (v0.1.0+)** | Brute-force/full-scan only (no HNSW/IVF yet); fast to "hundreds of thousands" of vectors per personal store — exactly the per-user on-device regime. Runs everywhere SQLite does. | **SHIP TODAY** | [sqlite-vec release](https://alexgarcia.xyz/blog/2024/sqlite-vec-stable-release/index.html) |
| **SQLCipher + WAL** | Standard AES-256 page encryption over SQLite, WAL for concurrent read/write. Mature, battle-tested. | **SHIP TODAY** | (well-established; pairs with sqlite-vec) |
| *Alt:* **Zvec (Alibaba, embedded)** | >8,000 QPS on Cohere-10M (>2× prior #1); SIMD/cache-friendly CPU. Newer (Feb 2026). | NEAR | [MarkTechPost](https://www.marktechpost.com/2026/02/10/alibaba-open-sources-zvec-an-embedded-vector-database-bringing-sqlite-like-simplicity-and-high-performance-on-device-rag-to-edge-applications/) |

**Verdict:** Fully shippable stack today: MiniLM-CoreML → sqlite-vec → SQLCipher+WAL. For your personal-memory scale (one user, hundreds of thousands of vectors max) sqlite-vec brute-force is fine; no ANN index needed. This matches your existing local-sentence-transformers setup.

## 5. Injection-layer web/knowledge enrichment APIs

| Option | Cost | Latency | Privacy | Source |
|---|---|---|---|---|
| **Brave Search API** | **$5 / 1k requests** (Search plan, $5/mo credits). **Free tier killed → metered billing.** | **95% < 1 s**; 50M searches/day infra | Strongest — no user profiling, Big-Tech-independent, own index | [Brave API](https://brave.com/search/api/), [implicator.ai](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/) |
| **Exa** | from **$2.5 CPM** but multi-factor (per-doc/crawl/summary surcharges → steep fast) | higher latency, smaller index | neural/semantic; no built-in answer synth | [search API comparison](https://awesomeagents.ai/pricing/search-api-pricing/) |
| **Tavily** | **$8 CPM** pay-as-you-go | longer latency, needs result cleanup | AI-agent-oriented | [firecrawl](https://www.firecrawl.dev/blog/tavily-alternatives) |
| **Wikipedia/Wikidata** | Free | network-bound | fully public, cacheable offline | (REST/SPARQL) |

**Verdict:** Brave is the privacy-aligned default for a privacy-first product (no profiling, own index, sub-1s). Note: **the free tier is gone — budget $5/1k.** For an injection layer that must preserve the on-device privacy story, prefer Wikipedia/Wikidata snapshots cached locally + Brave only for live lookups, so you don't leak the user's continuous context to a third party. The privacy posture of this layer is the single biggest threat to the "on-device" claim — every query leaves the device.

## 6. Continuous capture — thermal/power envelope (the real ceiling)

| Constraint | Real numbers | Device | Source |
|---|---|---|---|
| **Sustained SoC power** | A18 Pro peaks **8–10 W**, throttles to **~4–5 W sustained** to stay cool | A18 Pro | [chip comparison](https://erickimphotography.com/apple-m5-vs-a18-pro-comprehensive-chip-comparison/) |
| **Time-to-throttle (AR/camera)** | Throttling begins **~1 minute** into intensive compute at 70°F | iPhone 16 Pro | [Apple RoomPlan](https://machinelearning.apple.com/research/roomplan), AR throttling reports |
| **ARKit capture** | Apple explicitly documents capture frame-rate throttling tied to thermal state; RoomPlan's whole design goal was running all NNs on ANE (quantize/prune/NAS) specifically to avoid CPU/GPU throttle frame-drops | iPhone | [ARKit throttling doc](https://developer.apple.com/documentation/analytics-reports/arkit-capture-frame-rate-throttling), [RoomPlan](https://machinelearning.apple.com/research/roomplan) |

**Verdict — the hard physical wall:** Continuous camera + mic + VLM on an iPhone throttles in **~1 minute** and sustains only **~4–5 W**. A naive "always-on full-frame VLM" is thermally impossible. **Shippable continuous capture must:** (a) keep VLM duty-cycled to key/sharp frames, not every frame; (b) push perception onto the ANE (where OCR/ASR/embeddings already live cheaply); (c) treat the heavy VLM brain as async/bursty, not sustained. This is the hardware reason your existing live=bounded-helpers / brain=unbounded architecture is correct — it's not a design preference, it's a thermal constraint.

---

## Bottom line for Phase 2

**Shippable TODAY (build the spine on these):**
- OCR: ML Kit (0.05 s) or Apple Vision (0.31 s, +confidence) — your validated text-recall core sits here
- ASR: SpeechAnalyzer (iOS 26) / WhisperKit (2.2% WER, <0.5 s) — real-time
- Embeddings + store: MiniLM-CoreML + sqlite-vec + SQLCipher/WAL — your memory layer, fully local
- Injection: Brave ($5/1k, <1 s) for live; local Wikidata snapshot to protect privacy

**NEAR / qualified:**
- FastVLM-0.5B: fast TTFT, weights public, but Apple hid absolutes — benchmark before trusting; use on key frames only
- moondream2: works on iPhone but 4 s TTFT / <5 tok/s — async brain only, not live

**ASPIRATIONAL (do NOT promise):**
- Real-time (≥10 fps) on-device VLM captioning on iPhone — sub-5 tok/s decode + ~1-min thermal throttle make this impossible today
- Sustained always-on full-frame multimodal capture — capped at ~4–5 W; must duty-cycle

The single most load-bearing finding: **everything except the heavy VLM is genuinely real-time and on-device today.** The VLM is the one component that is both slow (sub-5 tok/s) and thermally expensive, which is exactly why a text/OCR-first, consensus-recall narrow product (your current pivot) is the honest shippable wedge — and why the VLM belongs in an async, duty-cycled brain rather than the live path.