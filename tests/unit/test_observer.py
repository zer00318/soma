from __future__ import annotations

import numpy as np
from PIL import Image

from trace_memory.capture import Observer, ObserverConfig


def _noise(seed: int, size: int = 64) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (size, size, 3), dtype=np.uint8)


def _gradient(size: int = 64) -> np.ndarray:
    row = np.linspace(0, 255, size, dtype=np.float64)
    g = np.tile(row, (size, 1))
    return np.stack([g, g, g], axis=2).astype(np.uint8)


def test_keeps_sharp_novel_frames():
    obs = Observer()
    assert obs.consider(_noise(1)).keep          # first sharp frame
    assert obs.consider(_noise(2)).keep is True   # different sharp scene


def test_drops_blurry():
    obs = Observer()
    d = obs.consider(_gradient())                 # smooth gradient -> ~0 Laplacian variance
    assert not d.keep and d.reason == "blurry"


def test_no_change_then_sleep():
    obs = Observer(ObserverConfig(sleep_after=3))
    frame = _noise(7)
    assert obs.consider(frame).keep               # first kept
    decisions = [obs.consider(frame) for _ in range(5)]  # identical -> no_change
    assert all(d.reason == "no_change" for d in decisions)
    assert decisions[-1].sleeping is True          # sustained no-change -> sleep


def test_drops_near_duplicate_view():
    obs = Observer()
    a = _noise(11)
    b = _noise(12)
    assert obs.consider(a).keep
    assert obs.consider(b).keep                    # different view, kept
    # a again: changed vs last-kept (b) but matches a recently-kept hash -> duplicate
    d = obs.consider(a)
    assert not d.keep and d.reason == "duplicate"


def test_select_from_dir_offline_analog(tmp_path):
    # 2 distinct sharp frames + a blurry one + a repeat -> keeps the 2 distinct.
    Image.fromarray(_noise(1)).save(tmp_path / "0001.jpg")
    Image.fromarray(_gradient()).save(tmp_path / "0002.jpg")     # blurry -> dropped
    Image.fromarray(_noise(2)).save(tmp_path / "0003.jpg")
    Image.fromarray(_noise(1)).save(tmp_path / "0004.jpg")       # dup of 0001 -> dropped
    kept = Observer().select_from_dir(tmp_path)
    names = {p.name for p in kept}
    assert "0001.jpg" in names and "0003.jpg" in names
    assert "0002.jpg" not in names


def test_stats_track_drops():
    obs = Observer()
    obs.consider(_noise(1)); obs.consider(_gradient())
    s = obs.stats()
    assert s["seen"] == 2 and s["kept"] == 1 and s["dropped"].get("blurry") == 1
