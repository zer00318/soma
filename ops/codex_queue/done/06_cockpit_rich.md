# CODEX BRIEF 06 — RICH honest cockpit (MORE detail, never less)

Branch: `codex/06-cockpit-rich`. Python via `.venv/bin/python`. Additive. Do NOT touch
`trace-native-fastvlm/` or `src/trace_memory/domain/`. The cockpit server is `scripts/cockpit_ask_server.py`
(serves :8799 from `ops/cockpit/*.json`). The founder wants the board RICHER — more distinct helpers and
more distinct things — and currently it shows "0 things" (it reads the cleared `kf_memory.json`) and a
shrunken helper list. Fix both and EXPAND.

## Tasks
1. **Real counts.** Make `scripts/cockpit_ask_server.py` `/api/status` report counts from the event log
   when present: scan `data/phone_captures/*/events.db` for observation count + distinct object subjects
   (the bound-entity count via `trace_memory.application.entity_binder.bind_entities`), falling back to
   `kf_memory.json` only if no events.db. Never show 0 when an events.db has rows.
2. **Full helper society (MORE).** Rewrite `ops/cockpit/agent_plan.json["helpers"]` to enumerate EVERY
   distinct helper/specialist with a status string, at least these 15 (add more if real):
   macro_vlm (Qwen2-VL-2B), ocr (Apple Vision), object_detector (YOLO), spatial_pose (CoreMotion),
   temporal, location_gps, audio_speech, ambient_sound, people_face, egomotion, binder_inject,
   premise_gate, two_zone_expand, persistence_eventlog, pii_scrub. Each: {name, role, status:
   live|partial|not-wired|demoted, evidence}.
3. **Critical path panel.** Add `agent_plan.json["critical_path"]` = the 7 CPs from
   `ops/PROTOTYPE_EXECUTION_ORACLE.md`, each {id, title, status, deliverable(D1/D2)}.
4. **Latest number.** Add `agent_plan.json["honest_number"]` read from
   `evaluation/results/scene_eval_latest.json` (N, correct%+CI, halluc%+CI, note it's FIXTURE not real).
5. **What's running.** Add `agent_plan.json["running"]` = {driver_alive, codex_active, queue_pending,
   last_committed_task} (compute via shell at status time, or write a tiny refresher).
6. Do NOT delete existing rich fields (tasks, plan, experiments, crew, vitals, jobs, recent_results) — keep + ADD.

## Acceptance (`tests/test_cockpit_rich.py`)
- `/api/status` (or the status builder function) returns a non-zero count when a fixture events.db with rows exists.
- `agent_plan.json["helpers"]` has >= 15 entries each with name+status; `critical_path` has 7 entries;
  `honest_number` present.

## Guardrails
- Additive; `pytest tests/ -q` must pass. Commit on branch (driver commits). Report what changed + the new helper/CP counts.
