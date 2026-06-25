# Cleanup Manifest

Date: 2026-06-25
Mode: Reversible archival cleanup; no file contents were edited.
Protected keep-set: Kept `trace-native-fastvlm/`, protected docs, protected scripts, and the recursive local import closure from `scripts/trace_brain_server.py`, `scripts/ask_home.py`, and `scripts/cockpit_ask_server.py`.

## Summary

- Root paths moved: 45
- Verification: `.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'src'); import ask_home, trace_brain_server; print('imports OK')"` returned `imports OK`

## Moved

- `trace_hub/` -> `archive/cleanup_20260625/trace_hub/`: Abandoned top-level hub tree not imported by the protected closure.
- `trace_perception/` -> `archive/cleanup_20260625/trace_perception/`: Abandoned top-level perception tree not imported by the protected closure.
- `web/` -> `archive/cleanup_20260625/web/`: Retired web tunnel assets not imported by the protected closure.
- `scripts/trace_app.py` -> `archive/cleanup_20260625/scripts/trace_app.py`: Retired tunnel entrypoint outside the keep-set.
- `scripts/phone_perceive.py` -> `archive/cleanup_20260625/scripts/phone_perceive.py`: Retired phone perception entrypoint outside the keep-set.
- `scripts/ask_home.py.bak.preassembler` -> `archive/cleanup_20260625/scripts/ask_home.py.bak.preassembler`: Backup snapshot outside the keep-set.
- `scripts/ask_home.py.bak.preleash` -> `archive/cleanup_20260625/scripts/ask_home.py.bak.preleash`: Backup snapshot outside the keep-set.
- `scripts/ask_home.py.bak.preupgrade` -> `archive/cleanup_20260625/scripts/ask_home.py.bak.preupgrade`: Backup snapshot outside the keep-set.
- `scripts/ask_home.py.bak.v1_leaky` -> `archive/cleanup_20260625/scripts/ask_home.py.bak.v1_leaky`: Backup snapshot outside the keep-set.
- `scripts/build_temporal_index.py.bak.v1` -> `archive/cleanup_20260625/scripts/build_temporal_index.py.bak.v1`: Backup snapshot outside the keep-set.
- `scripts/build_world_memory.py.bak.preupgrade` -> `archive/cleanup_20260625/scripts/build_world_memory.py.bak.preupgrade`: Backup snapshot outside the keep-set.
- `scripts/ops_cockpit.py.bak.prerevamp` -> `archive/cleanup_20260625/scripts/ops_cockpit.py.bak.prerevamp`: Backup snapshot outside the keep-set.
- `ops/sprint_measure/ask_home.py.bak-pre-leakfix` -> `archive/cleanup_20260625/ops/sprint_measure/ask_home.py.bak-pre-leakfix`: Backup snapshot outside the keep-set.
- `ops/CODEX_BRIEF_10_capture_pivot.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_10_capture_pivot.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_10_capture_pivot_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_10_capture_pivot_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_11_offline_world_fusion.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_11_offline_world_fusion.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_11_offline_world_fusion_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_11_offline_world_fusion_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_12_DRAFT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_12_DRAFT.md`: Historical Codex brief draft archived to reduce ops clutter.
- `ops/CODEX_BRIEF_12_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_12_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_12_trusted_naming.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_12_trusted_naming.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_12_trusted_naming_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_12_trusted_naming_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_13_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_13_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_13_pose_sharp_frames.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_13_pose_sharp_frames.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_13_pose_sharp_frames_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_13_pose_sharp_frames_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_14_capture_dashboard.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_14_capture_dashboard.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_14_capture_dashboard_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_14_capture_dashboard_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_2_dimensions_permanence.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_2_dimensions_permanence.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_3_permanence_bugfix.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_3_permanence_bugfix.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_4_durable_world.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_4_durable_world.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_5_spatial_post_reliability.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_5_spatial_post_reliability.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_6_spatial_pipeline_and_megavocab.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_6_spatial_pipeline_and_megavocab.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_7_naming_quality_and_renderer.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_7_naming_quality_and_renderer.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_8_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_8_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_8_phantom_judge.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_8_phantom_judge.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_8_phantom_judge_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_8_phantom_judge_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_9_dense_segmentation.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_9_dense_segmentation.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_9_dense_segmentation_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_9_dense_segmentation_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_cockpit_reality.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_cockpit_reality.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_dead_weight_audit.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_dead_weight_audit.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_entity_wiring.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_entity_wiring.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_entity_wiring_RESULT.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_entity_wiring_RESULT.md`: Historical Codex brief result archived to reduce ops clutter.
- `ops/CODEX_BRIEF_ops_dashboard.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_ops_dashboard.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_same_event_wiring.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_same_event_wiring.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_spatial_core.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_spatial_core.md`: Historical Codex brief archived to reduce ops clutter.
- `ops/CODEX_BRIEF_stage3_binding_probe.md` -> `archive/cleanup_20260625/ops/CODEX_BRIEF_stage3_binding_probe.md`: Historical Codex brief archived to reduce ops clutter.

## UNCERTAIN - left in place

- `evaluation/run_live.py`: Not in the keep-set, but it looks like a primary evaluation runner rather than abandoned experiment code.
- `evaluation/run_ras.py`: Not in the keep-set, but it looks like a primary evaluation runner rather than abandoned experiment code.
- `evaluation/run_north_star.py`: Not in the keep-set, but it looks like a primary evaluation runner rather than abandoned experiment code.
- `evaluation/founder_live_eval.py`: Not in the keep-set, but the founder-focused naming suggests a recent workflow.
- `evaluation/run_founder_gold_brain.py`: Not in the keep-set, but it appears tied to current founder-gold evaluation work.
- `evaluation/run_live_replay_battery.py`: Not in the keep-set, but it looks like an active replay battery entrypoint.
- `evaluation/posthoc_ablation.py`: Likely experiment code, but it may still back recent RAS comparisons.
- `evaluation/real_brain_probe.py`: Likely diagnostic experiment code, but the name suggests current manual use.
- `evaluation/ras/walk_outside_20260614.gold.json.bak-20260617-prefounder`: Backup eval artifact left in place because it may still be referenced for comparisons.
- `scripts/pitch_demo.html`: Could be demo collateral still used for current cockpit or pitch work.
- `scripts/pitch_progress.py`: Could be demo-progress tooling still used for current cockpit or pitch work.
- `scripts/trace_live_diagnostics.py`: Likely a current replacement for older live diagnostics tooling.
- `scripts/trace_night_shift.py`: Likely a current replacement for older night-shift tooling.
