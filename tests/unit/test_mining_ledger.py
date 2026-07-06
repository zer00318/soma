from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.mining_ledger import (  # noqa: E402
    GRID_COLS,
    GRID_ROWS,
    MAX_DEPTH_PASSES,
    MiningLedger,
)

SCENE = ("Brave Browser", "https://youtube.com/watch?v=x")


def test_static_scene_yields_progressively_deeper_tasks():
    led = MiningLedger()
    assert led.on_capture(SCENE, changed=True) is None    # novelty: breadth
    assert led.on_capture(SCENE, changed=False) is None   # not static enough yet
    tasks = []
    for _ in range(GRID_ROWS * GRID_COLS):
        t = led.on_capture(SCENE, changed=False)
        assert t is not None
        tasks.append(t)
    # every tile visited once before any tile repeats — least-mined first
    assert len({(t.tile_row, t.tile_col) for t in tasks}) == GRID_ROWS * GRID_COLS
    assert [t.depth for t in tasks] == list(range(1, GRID_ROWS * GRID_COLS + 1))
    # second sweep goes CLOSER (higher scale)
    t2 = led.on_capture(SCENE, changed=False)
    assert t2.scale > tasks[0].scale


def test_mined_dry_goes_quiet_and_novelty_resets():
    led = MiningLedger()
    led.on_capture(SCENE, changed=False)
    for _ in range(MAX_DEPTH_PASSES + 1):
        led.on_capture(SCENE, changed=False)
    assert led.on_capture(SCENE, changed=False) is None   # dry: budget respected
    assert led.on_capture(SCENE, changed=True) is None    # new content resets...
    led.on_capture(SCENE, changed=False)
    assert led.on_capture(SCENE, changed=False) is not None  # ...and mining restarts


def test_only_new_information_is_emitted():
    led = MiningLedger()
    led.seed_known(SCENE, ["YouTube", "Rao Bahadur (2026) Telugu DVDS"])
    fresh = led.novel_texts(SCENE, ["Rao Bahadur (2026) Telugu DVDS",
                                    "82k views", "Directed by S. Rajamouli"])
    assert fresh == ["82k views", "Directed by S. Rajamouli"]
    # a second pass over the same spans yields NOTHING — deepening, not repeating
    assert led.novel_texts(SCENE, ["82k views"]) == []
