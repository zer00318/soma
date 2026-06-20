P0: Phantom judge state and filtering are implemented; P0 iOS Release build succeeded.
P1: Spatial posts/ingest/API now carry w, h, support_plane, and verified; tests cover the full path.
P2: `where is X` spatial recall returns coordinate answers with spatial_pose citations; live DB mouse query works.
Risk: No device install or fresh device artifacts in this run, per brief; keyboard lacks a live spatial_pose row.
Blocked: Per-P commits and daemon restart were prevented by sandbox `.git`/process-control restrictions.
