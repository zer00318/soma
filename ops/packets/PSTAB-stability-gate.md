# P-STAB — stability root-cause + soak gate (merge gate for ALL app work)

Refounded order 2026-07-05, item 1. A memory prosthetic that freezes or dies
loses the day; stability is below table stakes until this packet's gate holds.

## Root cause — PROVEN from device analytics (pulled 2026-07-05, no founder tap needed)

`devicectl device info files --domain-type systemCrashLogs` on the founder's
phone, then `copy from`. Two reports, July 4 (the frozen-build day):

| report | launch | died | lifetime |
|---|---|---|---|
| FastVLM App-2026-07-04-141305.ips | 14:12:23 | 14:13:04 | **41 s** |
| FastVLM App-2026-07-04-155548.ips | 15:50:31 | 15:55:47 | **5 m 16 s** |

Identical stacks, both `bug_type 309` SIGABRT:

```
Cmlx  mlx::core::metal::check_error(MTL::CommandBuffer*)   ← throws C++ exception
  in MTL::CommandBuffer completion handler
  on queue com.Metal.CompletionQueueDispatch               ← not our thread
→ __cxa_throw → uncaught → std::terminate → abort
```

**The VLM inference stack (MLX/Metal, Qwen2.5-VL-3B) kills the app when a GPU
command buffer completes with an error.** Swift try/catch can never see it —
the throw happens on Metal's own completion queue. No JetsamEvent on July 4-5,
so it is NOT a system memory kill. The June 22-25 `UIKit-runloop-*.ips` hang
family is a separate (older-build) pathology; the "9-minute freeze" the chief
observed on 2026-07-05 is still unproven-cause (candidate: same GPU fault
manifesting as stall before abort, or an independent main-thread deadlock —
the soak decides).

What we do NOT know yet: the exception's `what()` string — the one fact that
discriminates GPU-memory exhaustion ("[metal::malloc] ...") from a
command-buffer execution failure/timeout. The .ips drops it and device syslog
needs root. Hence the black box (below).

## Landed in this packet (2026-07-05)

1. **Crash black box** — `trace-native-fastvlm/FastVLM App/CrashBlackBox.mm`:
   `std::set_terminate` handler, installed via static constructor, writes
   exception type + `what()` to `Documents/crash_blackbox.log` (static-buffer
   path, open/write only — safe in terminate context). Verified compiled +
   linked into the debug dylib; installed on device. **The next crash
   self-documents.**
2. **Soak rig** — `scripts/soak_stability.py`: per-tick JSONL to
   `evaluation/soak_history.jsonl`; watches (a) app PID via devicectl
   (verified live: 343 procs listed even when locked; file:// URL decode),
   (b) hub `/health` + latency, (c) store row-count ingest heartbeat. On a
   death it auto-pulls the newest .ips + the black-box log into
   `evaluation/soak_artifacts/` and (with `--relaunch`) restarts the app.
   Self-test PASS (2 ticks, hub alive, rows=3816 read).

## Soak #1 verdict (2026-07-05 18:40→22:40, black-box build, decomposed honestly)

Rig says FAIL (deaths=2, hub_failures=1); the decomposition says mostly-good:
- **ZERO crashes in 4h of continuous capture** — the July-4 MLX SIGABRT (41s /
  5m16s) did NOT reproduce; the black box never fired because nothing threw.
- Death 1 (21:15) REAL but not a crash: quiet iOS lifecycle reap ~2min after
  capture went idle (no .ips, no jetsam, no terminate; app had isIdleTimerDisabled;
  cause branch open: thermal reap vs background transition). Product problem =
  capture continuity, not code crash. Relaunch didn't retry (rig bug, fixed).
- Death 2 (22:25) FALSE: devicectl probe timeout counted as death — same PID
  alive 25min later. Rig fixed: PROBE_ERROR sentinel, probes that fail are
  silence not absence, carried state, never a death, never a relaunch trigger.
- hub_failure 1 = chief restarted the hub mid-soak for the pyramid router.
  LESSON (now law for soaks): a soak's infrastructure is FROZEN for its
  duration — no hub restarts, no daemon bounces, no deploys.
- max_ingest_gap 458s = phone idle while founder was on the Mac; reported
  honestly, not a failure.

**Soak #2 RUNNING overnight (22:41→06:41, 8h, fixed rig, --relaunch, infra
frozen).** Gate judgment lands with its verdict.

## The gate (Definition of Done)

- [ ] 4-hour soak, app in foreground capturing, **0 deaths, 0 hub failures**:
      `.venv/bin/python scripts/soak_stability.py --hours 4` → PASS row in
      `evaluation/soak_history.jsonl`. Until this passes, NO app-surface packet
      (P30/P31/P41, ask-v2) merges.
- [ ] `what()` string recovered from the first soak-provoked crash (black box)
      → root-cause note updated from "Metal command buffer error" to the exact
      failure, fix applied at the CAUSE (candidates, in evidence order:
      bound VLM inference cadence / skip-under-thermal-pressure; GPU memory
      cap via `MLX.GPU.set(memoryLimit:)`; MLX bump if upstream made
      completion-handler errors non-fatal).
- [ ] The 2026-07-05 "9-minute freeze" reproduced-or-cleared: if the soak
      shows a live PID with a dead feed (ingest gap while unlocked+capturing),
      that is the deadlock branch — pull a hang report and own it separately.

## Operational note

Phone was LOCKED at packet-authoring time. **MEASURED: the 1.7 GB devicectl
install STALLS against a locked phone over coredevice WiFi** (two attempts:
77 min no completion; 15-min self-abort) — yesterday's successful deploy ran
while the founder had the phone awake in iPhone Mirroring. So the black-box
build is built + verified but NOT yet on the device; install is part of the
founder-unlock step. Full sequence once the phone is unlocked (Mac, hub
already on keepalive):

```
xcrun devicectl device install app --device D3A506B2-8923-5313-B8A3-FF769ABBA228 \
  "trace-native-fastvlm/build/dd/Build/Products/Debug-iphoneos/FastVLM App.app"
xcrun devicectl device process launch --device D3A506B2-8923-5313-B8A3-FF769ABBA228 de.zer00.trace
.venv/bin/python scripts/soak_stability.py --hours 4 --relaunch
```
