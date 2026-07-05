# P30/P31/P41 — the product body: episodes, day digest, timeline

Refounded order 2026-07-05, item 2. The measured indictment: the founder can
see NOTHING of his past without typing a question and waiting ~30s. Spec v3's
phone app is "timeline of episodes (incl honest gaps) · multi-turn chat · live
retrieval narration · review cards". This packet builds the memory you can SEE.

Serial inside the packet (each stage lands + tests green before the next):

## Stage A — P30 episode segmentation (Mac, sleep-time, no app work → not soak-gated)
`src/trace_memory/brain/episodes.py` + wired into `scripts/nightly_sleep.py`.
- Input: consolidated store rows (all channels). Output: `episode` derived rows
  (reconsider-able, same discipline as binder derived rows — never destructive).
- Boundary signals, in strength order: capture-session start/stop; ingest gaps
  > measured threshold; anchor/room change (P10 grades); scene-shift from
  track-population turnover. Thresholds scale with measured noise (jar-saga rule).
- **MEASURED 2026-07-05 on the real store (3736 raw obs, 10 capture days):**
  gap distribution is bimodal — within-capture gaps are <60s in 3014/3104
  cases; 61 gaps ≥5min (clear session boundaries, up to 81h); 29 gaps in the
  1–5min ambiguous middle. Stage-A starting thresholds: **≥5min gap = hard
  episode boundary; 1–5min = soft boundary** (split only if corroborated by
  place/anchor change, else same episode). Re-measure once multi-hour natural
  carries exist — today's data is dev-session-shaped.
- HONEST GAPS are first-class: a gap between episodes is itself an episode row
  ("no capture, 2h 14m") — the timeline must never paper over blindness.
- Naming: cheap deterministic label from dominant room + dominant activity
  tokens + time-of-day ("desk work, Tuesday morning"); NO content lexicons in
  ranking paths (M3 law) — labels are display-only metadata.
- DoD: episodes over the real 3.8k-row store eyeballed against the founder's
  actual July days; pytest unit coverage on boundary logic; battery held.

## Stage B — P31 minimal day digest (Mac, sleep-time)
- Per day: episode list → one `digest_day` derived row: 3-6 bullet summary,
  each bullet citing its episode ids (receipts discipline — same as /ask).
- Local gemma writes prose FROM structured episode facts only (no raw-store
  free association); refusal-honest: thin day → "mostly uncaptured".
- DoD: digest for each of the last 3 real capture days reads true vs the
  store; zero uncited claims; battery held.

## Stage C — P41 timeline surface (iOS — SOAK-GATED: merges only after P-STAB PASS)
- Open app → TODAY: episode cards (name, time span, room, thumbnail-free — no
  frames exist by L1) + gap cards, newest first; pull older days.
- Tap episode → its evidence rows (the P40 receipt component, reused).
- Hub additions: `GET /episodes?day=` + `GET /digest?day=` (read-only, served
  from derived rows — no ask-brain invocation, must return <300ms).
- DoD: founder opens app after a real carry and SEES his day without typing;
  feed shows honest gaps; iOS build green; device-render verified.

Dependencies: none on P12/P13 (episodes read whatever the store has).
Executor: Stage A judgment (chief/Fable) · Stage B guided · Stage C judgment.
