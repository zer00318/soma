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
| P10 | [Coordinate anchor substrate](P10-anchor-substrate.md) | judgment | Fable / Opus high | P00 | REVIEW — CODE LANDED 2026-07-04 (chief): Mac substrate (anchors table + record_anchor + graded, monotone, cross-session relocalization; both ingest shapes pin via one owner) 288 pytest green + battery 96.7/100/0/100 held; Swift `spatialStamp()` promotes ARKit→contract fields at the POST funnel, iOS build green. DEVICE-PROOF PENDING (packet checklist: 2-min walk → ≥80% coverage + re-entered-room relocalize) → then MERGED |
| P11 | [Appearance fingerprints](P11-appearance-fingerprints.md) | guided | Opus medium | P00 | READY (P00 GREEN) |
| P12 | [Live binder](P12-live-binder.md) | judgment | Fable | P10,P11,P02 | BLOCKED |
| P13 | [Look-again loop](P13-look-again.md) | guided | Opus medium | P12 | BLOCKED |

## W2 — Coverage wave one (parallel once P02 lands; each is independent)

| id | packet | tag | executor · effort | depends | status |
|---|---|---|---|---|---|
| P20 | [Mac screen daemon](P20-mac-screen-daemon.md) | guided | Opus medium | P02 | BLOCKED(P02) |
| P21 | [Voice-identity clustering](P21-voice-identity.md) | judgment | Opus high | P02 | BLOCKED(P02) |
| P22 | [Motion/IMU channel](P22-motion-channel.md) | mechanical | Sonnet/local | P02 | BLOCKED(P02) |
| P23 | [Ambient sound events](P23-sound-events.md) | guided | Sonnet/Opus medium | P02 | BLOCKED(P02) |
| P24 | [Activity dispatcher v1](P24-activity-dispatcher.md) | judgment | Fable / Opus high | P02, one of P20-P23 | BLOCKED |

## W3 — Memory organs (STUBS — spec §0.4: authored in full only when W2 numbers are in)
- P30 episode segmentation (place+motion+scene shifts → named episodes; honest gap episodes)
- P31 digest pyramid + pyramid router in ask brain (episode→day→week; climb-then-drill)
- P32 identity-resolution brain (cross-source merge, auto/ask policy, review-card queue)
- P33 multi-turn ask + retrieval-narration events streamed from /ask

## W4 — The app (STUBS)
- P40 chat screen (narrate → badge → receipts) · P41 timeline w/ gap honesty ·
- P42 review cards (3 channels) · P43 hide-then-purge delete

## W5 — Finish line (STUBS)
- P50 3-day capture ops runbook · P51 blind-battery protocol + scoring · P52 demo choreography

## Leash audit log
- (appended every 5 merges: date · packets · did any domain number move · verdict)
