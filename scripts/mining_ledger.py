#!/usr/bin/env python3
"""N2 — the mining ledger: the stare economy's bookkeeper (pure, testable).

Founder law (re-founding 2026-07-06): a static scene must yield MORE per
frame, never the same labels again. The ledger tracks, per scene, how long it
has been static and which tiles have been depth-mined; each static tick it
hands back ONE DepthTask — the least-mined tile next — so successive frames
of the same scene CONTINUE where the last stopped instead of repeating.

Novelty resets the ledger (breadth beats depth on a new scene). Depth is
bounded per scene (MAX_DEPTH_PASSES) — after the scene is mined dry the
ledger goes quiet instead of burning budget on noise. Consumers: the Mac
screen daemon v1 (tile crop-zoom OCR); the phone's EnrichmentScheduler is the
twin seam (targeted VLM crops per track).
"""

from __future__ import annotations

from dataclasses import dataclass, field

GRID_ROWS = 3
GRID_COLS = 3
STATIC_TICKS_BEFORE_MINING = 2   # scene unchanged this many ticks -> start depth
MAX_DEPTH_PASSES = 2 * GRID_ROWS * GRID_COLS  # every tile at 2x, then quiet


@dataclass(frozen=True)
class DepthTask:
    tile_row: int
    tile_col: int
    depth: int      # 1-based pass number for this scene
    scale: int      # upscale factor for this pass (deeper = closer look)


@dataclass
class _SceneState:
    static_ticks: int = 0
    passes_done: int = 0
    tile_counts: dict = field(default_factory=dict)  # (r,c) -> times mined
    mined_hashes: set = field(default_factory=set)   # text already extracted


class MiningLedger:
    """One ledger per capture daemon. Keyed by scene (app, url/window)."""

    def __init__(self) -> None:
        self._scenes: dict = {}

    def on_capture(self, scene_key: tuple, changed: bool) -> DepthTask | None:
        """Called every capture tick. Returns the next DepthTask when the
        scene has been static long enough and mining budget remains."""
        state = self._scenes.setdefault(scene_key, _SceneState())
        if changed:
            # novelty: breadth wins, depth restarts (the scene is new content)
            state.static_ticks = 0
            state.passes_done = 0
            state.tile_counts = {}
            return None
        state.static_ticks += 1
        if state.static_ticks < STATIC_TICKS_BEFORE_MINING:
            return None
        if state.passes_done >= MAX_DEPTH_PASSES:
            return None  # mined dry — stay quiet until the scene changes
        # least-mined tile first; row-major tiebreak keeps it deterministic
        tiles = [(state.tile_counts.get((r, c), 0), r, c)
                 for r in range(GRID_ROWS) for c in range(GRID_COLS)]
        tiles.sort()
        _, r, c = tiles[0]
        state.tile_counts[(r, c)] = state.tile_counts.get((r, c), 0) + 1
        state.passes_done += 1
        return DepthTask(tile_row=r, tile_col=c,
                         depth=state.passes_done,
                         scale=2 + state.tile_counts[(r, c)] - 1)

    def novel_texts(self, scene_key: tuple, texts: list) -> list:
        """Which of these mined texts are NEW for this scene? Marks them mined.
        The whole point of deepening: only new information gets emitted."""
        state = self._scenes.setdefault(scene_key, _SceneState())
        fresh = []
        for t in texts:
            h = " ".join(t.lower().split())
            if len(h) >= 4 and h not in state.mined_hashes:
                state.mined_hashes.add(h)
                fresh.append(t)
        return fresh

    def seed_known(self, scene_key: tuple, texts: list) -> None:
        """Seed the mined-set with what BREADTH already saw, so depth passes
        emit only what breadth missed."""
        state = self._scenes.setdefault(scene_key, _SceneState())
        for t in texts:
            h = " ".join(t.lower().split())
            if len(h) >= 4:
                state.mined_hashes.add(h)
