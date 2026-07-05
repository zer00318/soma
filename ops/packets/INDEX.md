# PACKET LEDGER — the only live work-tracking doc (law: ops/CANONICAL_SPEC.md §7)

Rules: one packet = one file here. Executors flip ONLY their own status cell.
Status: READY · IN-PROGRESS(who) · REVIEW · MERGED(commit) · REVERTED(why) · BLOCKED(dep).
Tags → executor/effort (spec §7): mechanical = local LLM/Sonnet (Opus low) ·
guided = Sonnet or Opus medium · judgment = Opus high (agent teams OK) or Fable.
Merge gate for every packet: pytest green + canonical battery CONFIDENT-WRONG = 0 +
real-store spot check for perception/brain packets. The Leash (§6) audits every 5 merges.

## W0 — Foundations & spikes (active)

| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P00 | [ARKit-as-camera-owner spike](P00-spike-arkit-camera-owner.md) | judgment | Opus high / Fable | — | GREEN 2026-07-04: 85% Tracking, all 4 channels alive on ARKit frames, counters live. W1 unblocked |
| P01 | [Repo hygiene](P01-repo-hygiene.md) | mechanical | local/Sonnet | — | MERGED (with P04 commit): strays deleted, wal/shm gitignore fences; writer was one-off Jul-1 audit tooling |
| P02 | [Helper contract + registry](P02-helper-contract-registry.md) | judgment | Fable | — | MERGED 2026-07-04: contract.py + config/helpers.json (11 helpers) + dual-shape ingest + pillar-aware ask fence + example plugin proven live (unregistered kettle-watcher cited by /ask). 257 tests, battery held |
| P03 | [The Leash v1](P03-leash-v1.md) | guided | Opus medium | P02 ✓ | MERGED 2026-07-04 (opus agent, ed057d8): evaluation/leash.py + history + 15 tests; first live signal = digital/motion/sound/temporal STARVED; yank arms at 5 merges |
| P05 | [Speech quality: whole utterances](P05-speech-quality.md) | guided | Opus medium | — | MERGED 2026-07-04 (opus agent, 35fd1a1): utterance-boundary commits + iOS26 SpeechAnalyzer behind flag + sleep stitcher (7 tests). Engine WER numbers device-pending (flip flag + read script) |
| P06 | [Style debt: pre-push hook green](P06-style-debt.md) | mechanical | local/Sonnet | P03 ✓ P05 ✓ | READY — dispatch to local fleet anytime |
| P04 | [Ask-brain over-refusal fixes](P04-askbrain-overrefusal.md) | judgment | Opus high / Fable | — | MERGED: all 4 defects owned (temporal-qualifier 457f9f2; existence-present + channel + compound + text-token anchor-poisoning fix). Where-is resolved = harness artifact (heuristic reasoner) + missing sleep run; live hub answers 'on a gray surface and a table' @0.9 |

## W1 — Substrate & live binder (author fully when W0 numbers are in)

| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P10 | [Coordinate anchor substrate](P10-anchor-substrate.md) | judgment | Fable / Opus high | P00 | MERGED 2026-07-04 (20c3311): device-proven BOTH checklist items — walk coverage 84% ≥ gate, grade `world` relocalization live (arkit:world:8022BFB0, after grace 10→30s fix); 3-jar identity substrate proven in choreographed AND natural regimes; per-track raycast + box extents emitted. Cross-session constellation alignment = follow-on packet |
| P11 | [Appearance fingerprints](P11-appearance-fingerprints.md) | guided | Opus medium | P00 | MERGED 2026-07-04 with MEASURED VERDICT: featureprint is a CATEGORY signal, NOT an instance signal (3-identical-jars ROC: same-kind cosines overlap cross-kind; no split threshold exists). Role = same-kind corroborator + retrieval; individuation belongs to coordinates. No perception tax measured. Tight crop landed |
| P12 | [Live binder](P12-live-binder.md) | judgment | Fable | P10,P11,P02 | IN-PROGRESS(chief) — Mac core MERGED (global identity graph + regime-proof natural-motion rules, 20c3311; 3 jars resolved exactly in both regimes; honest [low,high] counts). REMAINING: at-ingest live hints + instant-disjointness floor from box extents |
| P13 | [Look-again loop](P13-look-again.md) | guided | Opus medium | P12 | BLOCKED(P12) |

## W2 — Coverage wave one (parallel once P02 lands; each is independent)

| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P20 | [Mac screen daemon](P20-mac-screen-daemon.md) | guided | Opus medium | P02 | BLOCKED(P02) |
| P21 | [Voice-identity clustering](P21-voice-identity.md) | judgment | Opus high | P02 | BLOCKED(P02) |
| P22 | [Motion/IMU channel](P22-motion-channel.md) | mechanical | Sonnet/local | P02 | BLOCKED(P02) |
| P23 | [Ambient sound events](P23-sound-events.md) | guided | Sonnet/Opus medium | P02 | BLOCKED(P02) |
| P24 | [Activity dispatcher v1](P24-activity-dispatcher.md) | judgment | Fable / Opus high | P02, one of P20-P23 | BLOCKED |

## COURSE CORRECTION 2026-07-04 (founder: "think product as a whole; stop bandaging one fix")
Substrate depth is FROZEN at honest-ranges quality (individuation is regime-proof; box-extent
data accrues passively from normal use). The Leash's first live signal already said it:
digital/motion/sound/temporal channels are STARVED while jar-counting got three sessions.
Rebalanced order: (1) P40 phone ask surface FIRST (pulled forward from W4 — the product loop
the founder touches; without it there is no product, only a lab), (2) P30/P31 minimal digest
so each daily carry yields "what happened today", (3) start the 3-real-days clock immediately,
(4) P22/P23 dispatched to the agent fleet in parallel (mechanical, starving), (5) P12-live +
P13 fed by real usage gaps, (6) founder blind battery on the 3-day store = the number.

## REFOUNDED ORDER 2026-07-05 (founder-ordered brutal step-back; eyes-on-device + Leash)
Measured facts that forced it: old build frozen 9+ min on the real phone; Leash run
2026-07-05 = physical 2756 FED vs digital/motion/sound/temporal ZERO (tunnel measured,
4 packets since last domain move — yank arms at 5); app is a pipeline console, not the
spec's browsable product. New serial order:
(1) **P-STAB** stability gate — see below — merge gate for ALL app-surface work,
(2) P30/P31 minimal episodes + day digest AND P41 TIMELINE (the memory you can SEE),
(3) ask-v2 <2s fastpaths + streamed retrieval narration,
(4) P20 Mac screen daemon (digital half, Leash-starved), then P22/P23 fleet,
(5) 3-day clock + founder blind battery (unchanged done bar).

| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P-STAB | [Stability root-cause + soak gate](PSTAB-stability-gate.md) | judgment | Fable/chief | — | IN-PROGRESS(chief) 2026-07-05: ROOT CAUSE PROVEN from device .ips (MLX `check_error` throws on Metal completion queue → SIGABRT; 41s + 5m16s lifetimes July 4; NOT jetsam). Crash black box (CrashBlackBox.mm) built+installed; soak rig scripts/soak_stability.py self-tested. REMAINING: founder unlock → install (1.7GB stalls against a locked phone — measured 2×) → launch → 4h soak PASS + what() string → causal fix |
| P30/31/41 | [Product body: episodes + digest + timeline](P30-31-41-product-body.md) | judgment | Fable/chief | Stage C gated on P-STAB PASS | Stage A LANDED 2026-07-05: store/episodes.py (EpisodeBuilder, measured 5min-hard/1-5min-soft-with-place thresholds, honest GAP episodes, reconsiderable builder="episodes") + nightly wiring + 3 unit tests. REAL-STORE PROOF: 64 episodes/61 gaps/10 days read true — the 07-04 14:12-14:13 episode ends AT the proven MLX crash (14:13:04), segmentation corroborates device evidence. Ask spot-check: answers byte-identical with/without episode rows. Stage B LANDED same day: store/digest.py (DigestBuilder: gemma prose from episode facts ONLY, uncited bullets dropped, thin-day honesty, blind-time note; deterministic fallback) + nightly wiring + 2 tests. REAL-STORE PROOF: 10 digest days, last-3-days bullets all cited + true. NEXT: Stage C timeline (SOAK-GATED) |

## W3 — Memory organs (STUBS — spec §0.4: authored in full only when W2 numbers are in)
- P30 episode segmentation (place+motion+scene shifts → named episodes; honest gap episodes)
- P31 digest pyramid + pyramid router in ask brain (episode→day→week; climb-then-drill)
- P32 identity-resolution brain (cross-source merge, auto/ask policy, review-card queue)
- P33 multi-turn ask + retrieval-narration events streamed from /ask

## W4 — The app (P40 pulled forward — it IS the product loop)
| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P40 | [Phone ask surface](P40-chat-ask-surface.md) | judgment | Fable/chief | P02, hub /ask | REVIEW — LANDED 2026-07-04: phone ask is now a CHAT thread (AskTurn/AskReceipt/AskTurnView) with calibrated badge + confidence + expandable receipts; hub POST /ask enriched with when/helper/text; verified live ("how many bottles" → "between 2 and 3" hedged 0.5 + receipt). iOS build green. DEVICE-RENDER PENDING (phone→hub round-trip on next carry) → MERGED |
- P41 timeline w/ gap honesty · P42 review cards (3 channels) · P43 hide-then-purge delete

## W5 — Finish line
| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P50 | 3-day capture ops runbook → [ops/RUNBOOK_3DAY.md](../RUNBOOK_3DAY.md) | judgment | Fable/chief | — | LANDED 2026-07-04 from the readiness audit. Four blockers found+fixed: (1) offline spool NEVER drained + replay script didn't exist → phone auto-drains on hub-healthy (8s loop, bounded chunks, capture-time preserved); (2) sleep binder never ran automatically → scripts/nightly_sleep.py (backup→consolidate→battery→log) + cron line; (3) brain unproven at multi-day scale → evaluation/scale_probe_3day.py (23k rows): latency OK (~37s worst, gemma-bound), found+fixed "yesterday" window-browse owner, S1 temporal-grounding refusal, plain-form before/after firm-wrong; (4) hub died with Mac sleep → scripts/run_hub_keepalive.sh (restart loop + caffeinate) + mDNS hub URL |
- P51 blind-battery protocol + scoring · P52 demo choreography (STUBS)

## Leash audit log
- (appended every 5 merges: date · packets · did any domain number move · verdict)
