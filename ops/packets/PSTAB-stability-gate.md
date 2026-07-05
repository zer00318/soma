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

Phone was LOCKED at packet-authoring time; install of the black-box build
succeeded, launch requires one founder unlock. Soak start command (Mac,
hub already on keepalive):

```
xcrun devicectl device process launch --device D3A506B2-8923-5313-B8A3-FF769ABBA228 de.zer00.trace
.venv/bin/python scripts/soak_stability.py --hours 4 --relaunch
```
