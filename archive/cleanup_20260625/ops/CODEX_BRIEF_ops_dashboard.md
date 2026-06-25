# CODEX BRIEF — Glanceable OPS dashboard (the founder's mission-control view)

The founder called the current `/engine` page "very very subpar." Build a genuinely GLANCEABLE
operations dashboard so that in ~5 seconds the founder can see: **is it working, what is the Chief
doing right now, when does it come back, what's the plan, what's blocked, and the honest progress.**
This is mission control for an autonomous agent, not a metrics dump.

## Where
Add a route `/ops` (HTML) and `/ops.json` (the merged live status as JSON) to
`scripts/cockpit_ask_server.py` (you added `/engine` here last time — same pattern, same do_GET). Keep
`/engine` and the investor demo working. Make `/ops` the page the founder lands on for monitoring.

## Data sources (merge these LIVE on every request — do not cache)
1. `ops/cockpit/agent_plan.json` — what the Chief is doing / plan / blocked-on-founder / job patterns.
   (Author maintains this; read it fresh each request. Degrade gracefully if missing.)
2. LIVE process state — for each entry in agent_plan.json `jobs`: shell out (`pgrep -f <pattern>` /
   `ps`) to get ALIVE/DEAD + pid + elapsed + %cpu. Show a green dot if alive, red if dead.
3. For jobs with `progress` files, read each JSON and show compact progress
   (e.g. `day 19/19 done (2✔ 3✘ 14–)  walk 8/25…`). Read `state/done/total/correct/wrong/miss`.
4. ollama: parse `ollama ps` → loaded model + processor, or "idle". Machine: `uptime` load averages +
   the single top-CPU process (`ps aux | sort -nrk3 | head`).
5. `ops/cockpit/engine.json` — the honest number (or UNMEASURED) + the 6-stage pipeline states +
   the two deliverables (demo READY vs number).

## Layout (glanceable — big type, color dots, scannable; NO dense paragraphs, NO repo trivia)
- **Top banner:** one big line — overall `status` (working=green / blocked=amber / idle=gray) + `headline`
  + "updated Ns ago". The single most important glance.
- **RUNNING NOW:** the jobs list with alive/dead dots, pid, elapsed, %cpu, the `does` line, and progress.
  Then a thin machine-health strip (load avg, ollama model/idle, top CPU proc).
- **WHAT THE CHIEF IS DOING:** `doing_now`, `current_task`, `next_action`, `next_wake` — this answers
  "what are you doing and when do you come back."
- **THE PLAN:** ordered `plan` with state badges (now=green / blocked=amber+note / done=gray). Then a
  highlighted **NEEDS YOU** box from `blocked_on_founder`.
- **PROGRESS:** the honest number (big; show UNMEASURED/in-progress honestly), the 6 pipeline stages as
  compact colored dots with labels, demo READY vs number. Link to `/engine` for detail.

## Requirements
- Auto-refresh every 5s (meta refresh or a small fetch loop on `/ops.json`).
- Dark-friendly, readable on a phone, flat (no gradients). Big enough to read across a room.
- Robust: any missing file/field → show "—" or "unknown", never crash the page.
- `/ops.json` returns the same merged data as JSON (so the founder/Chief can curl it).

## Verify (and report)
- Do an in-process handler check (like last time) that `/ops` returns 200 and contains the running-job
  name, the plan, and the number; `/ops.json` parses. (You cannot reach localhost from the sandbox —
  the author will restart the server and verify in the browser; just confirm the handler logic.)
- Report: files changed, the routes added, and confirm the page degrades gracefully if a source JSON
  is absent. Do not overstate. Honesty over polish — but this one must ALSO be genuinely glanceable.
