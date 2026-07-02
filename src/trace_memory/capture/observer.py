"""The capture observer — a cheap, always-on triage stage that runs on EVERY frame and
forwards only the few worth expensive perception.

This is the bridge between the offline demo and the live product: the same gate ladder runs
over a stored clip (demo) or a live stream (product). It is pure CV — no LLM, no GPU — so it
can run on-device and 24/7. The expensive helpers (crop-zoom perception, the local-LLM binder,
the reasoner) only ever see frames the observer keeps.

Gate ladder, cheapest first (fail-fast):
  1. blur      — variance-of-Laplacian below threshold -> drop
  2. exposure  — too dark / blown out -> drop
  3. change    — too similar to the last KEPT frame -> drop (sustained -> "sleep")
  4. duplicate — average-hash within Hamming radius of a recently kept frame -> drop

Frames are read in memory; the observer never persists pixels (privacy moat).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def _to_gray(image: "str | Path | np.ndarray | Image.Image") -> np.ndarray:
    if isinstance(image, np.ndarray):
        arr = image
        if arr.ndim == 3:
            arr = arr.mean(axis=2)
        return arr.astype(np.float64)
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("L"), dtype=np.float64)
    return np.asarray(Image.open(image).convert("L"), dtype=np.float64)


def sharpness(image: Any) -> float:
    """Variance-of-Laplacian (higher = sharper). Matches scripts/frame_quality.py."""
    g = _to_gray(image)
    k = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)
    from numpy.lib.stride_tricks import sliding_window_view

    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    windows = sliding_window_view(g, (3, 3))
    lap = (windows * k).sum(axis=(-1, -2))
    return float(lap.var())


def brightness(image: Any) -> float:
    return float(_to_gray(image).mean())


def _ahash(image: Any, hash_size: int = 8) -> int:
    g = np.asarray(
        (image if isinstance(image, Image.Image) else Image.open(image) if not isinstance(image, np.ndarray)
         else Image.fromarray(image.astype(np.uint8))).convert("L").resize((hash_size, hash_size)),
        dtype=np.float64,
    )
    bits = (g > g.mean()).flatten()
    out = 0
    for b in bits:
        out = (out << 1) | int(b)
    return out


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _change_score(prev_small: np.ndarray | None, small: np.ndarray) -> float:
    """Mean absolute difference (0..1) vs the last kept frame's downscaled grayscale."""
    if prev_small is None:
        return 1.0
    return float(np.abs(small - prev_small).mean() / 255.0)


@dataclass
class ObserverConfig:
    blur_threshold: float = 60.0          # variance-of-Laplacian; below = blurry
    dark_threshold: float = 12.0          # mean brightness; below = too dark
    bright_threshold: float = 245.0       # mean brightness; above = blown out
    change_threshold: float = 0.04        # MAD vs last kept frame; below = "no change"
    dup_hamming: int = 4                  # avg-hash Hamming distance; <= = near-duplicate
    sleep_after: int = 8                  # consecutive no-change frames -> sleeping
    small_size: int = 32                  # downscale for the change gate
    dup_memory: int = 12                  # how many recent kept hashes to compare against


@dataclass
class ObserverDecision:
    keep: bool
    reason: str           # "kept" | "blurry" | "dark" | "bright" | "no_change" | "duplicate"
    sleeping: bool        # scene is idle (sustained no-change) -> helpers can idle
    sharpness: float = 0.0
    change: float = 0.0


@dataclass
class Observer:
    """Stateful per-stream observer. Call ``consider(frame)`` for each incoming frame."""

    config: ObserverConfig = field(default_factory=ObserverConfig)
    _last_small: np.ndarray | None = field(default=None, init=False, repr=False)
    _recent_hashes: list[int] = field(default_factory=list, init=False, repr=False)
    _no_change_run: int = field(default=0, init=False, repr=False)

    # --- counters for telemetry / "what was dropped" honesty ---
    seen: int = field(default=0, init=False)
    kept: int = field(default=0, init=False)
    dropped: dict[str, int] = field(default_factory=dict, init=False)

    def _drop(self, reason: str, sleeping: bool, sharp: float, change: float) -> ObserverDecision:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1
        return ObserverDecision(False, reason, sleeping, sharp, change)

    def consider(self, image: Any) -> ObserverDecision:
        self.seen += 1
        cfg = self.config
        img = Image.open(image).convert("RGB") if isinstance(image, (str, Path)) else (
            image if isinstance(image, Image.Image) else Image.fromarray(np.asarray(image).astype(np.uint8))
        )

        sharp = sharpness(img)
        if sharp < cfg.blur_threshold:
            return self._drop("blurry", self._no_change_run >= cfg.sleep_after, sharp, 0.0)

        bright = brightness(img)
        if bright < cfg.dark_threshold:
            return self._drop("dark", self._no_change_run >= cfg.sleep_after, sharp, 0.0)
        if bright > cfg.bright_threshold:
            return self._drop("bright", self._no_change_run >= cfg.sleep_after, sharp, 0.0)

        small = np.asarray(img.convert("L").resize((cfg.small_size, cfg.small_size)), dtype=np.float64)
        change = _change_score(self._last_small, small)
        if change < cfg.change_threshold:
            self._no_change_run += 1
            return self._drop("no_change", self._no_change_run >= cfg.sleep_after, sharp, change)

        h = _ahash(img)
        if any(_hamming(h, prev) <= cfg.dup_hamming for prev in self._recent_hashes):
            # changed vs immediate last-kept but matches a recently-kept view -> redundant
            return self._drop("duplicate", False, sharp, change)

        # KEEP: a sharp, well-exposed, novel frame. Reset the sleep counter, update memory.
        self._no_change_run = 0
        self._last_small = small
        self._recent_hashes.append(h)
        if len(self._recent_hashes) > cfg.dup_memory:
            self._recent_hashes.pop(0)
        self.kept += 1
        return ObserverDecision(True, "kept", False, sharp, change)

    def select_from_dir(self, frames_dir: "str | Path", pattern: str = "*.jpg") -> list[Path]:
        """Offline analog: run the live gate ladder over a stored clip, in capture order."""
        frames = sorted(Path(frames_dir).glob(pattern), key=lambda p: p.stem)
        return [f for f in frames if self.consider(f).keep]

    def stats(self) -> dict[str, Any]:
        return {"seen": self.seen, "kept": self.kept, "dropped": dict(self.dropped),
                "keep_rate": round(self.kept / self.seen, 3) if self.seen else 0.0}
