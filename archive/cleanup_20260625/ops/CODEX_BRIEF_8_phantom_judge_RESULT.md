# CODEX BRIEF 8 RESULT - phantom judge

Status: P0, P1, and P2 implemented in the worktree. Device install was not performed because the brief says the lead installs; therefore there are no fresh device artifacts proving `phantom_marked` on hardware from this run.

P0 shipped in `SpatialWorld.swift`: `SpatialObject` now persists `phantomStrikes` and `phantom`, FastVLM no-object/cannot-see outputs count distinct crop strikes, 3 strikes mark `phantom_marked`, successful verified/relabel results clear phantom state, phantom objects are excluded from words/posts, and status shows `ph:N`. P0 iOS Release build: `BUILD SUCCEEDED`.

P1 shipped: Swift spatial posts include `support_plane` alongside existing `w`, `h`, and `verified`; hub ingest stores those keys in `spatial_pose`; `/api/world` passes them through. Unit fixture verifies post -> `spatial_pose` -> `/api/world`.

P2 shipped: `where is/where's/where was/wo ist` routes to graph spatial recall, fuzzy-matches object labels with `spatial_pose`, returns extractive coordinate answers with spatial citations, and falls back to the standard honest miss. Live DB check: `where is the mouse` returns coordinates + `spatial_pose` citation; `where is the keyboard` does not, because the live DB currently has no keyboard spatial_pose row.

Verification: `python3 -m unittest discover -s tests -p "test_*.py"` -> 124 tests OK. `python3 evaluation/run_north_star.py` exits 0 at the pre-existing 9/10 = 0.90. P1 iOS Release build: `BUILD SUCCEEDED`.

Operational blockers: `.git` is read-only in this sandbox, so required per-P commits failed at `.git/index.lock`. Process control is also blocked (`kill` and `pgrep` denied), so existing hub/dashboard daemons could not be restarted after `graph.py`; attempted replacement processes failed to bind while old listeners remained on :8765/:8777.
