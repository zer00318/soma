"""Deterministic frame quality scoring for intake gating."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


_MAX_SIDE = 512

try:
    _BILINEAR = Image.Resampling.BILINEAR
except AttributeError:  # Pillow < 9.1
    _BILINEAR = Image.BILINEAR


def _image_to_pil(image: str | Path | np.ndarray[Any, Any]) -> Image.Image:
    if isinstance(image, (str, Path)):
        with Image.open(image) as opened:
            pil_image = opened.copy()
    else:
        array = np.asarray(image)
        if array.ndim not in (2, 3):
            raise ValueError("image array must be HxW or HxWxC")
        if array.ndim == 3 and array.shape[2] not in (1, 3, 4):
            raise ValueError("image array channel count must be 1, 3, or 4")
        if array.dtype != np.uint8:
            array = np.clip(np.rint(array), 0, 255).astype(np.uint8)
        if array.ndim == 2:
            pil_image = Image.fromarray(array, mode="L")
        elif array.shape[2] == 1:
            pil_image = Image.fromarray(array[:, :, 0], mode="L")
        elif array.shape[2] == 3:
            pil_image = Image.fromarray(array, mode="RGB")
        else:
            pil_image = Image.fromarray(array, mode="RGBA")

    width, height = pil_image.size
    max_side = max(width, height)
    if max_side > _MAX_SIDE:
        scale = _MAX_SIDE / float(max_side)
        new_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        pil_image = pil_image.resize(new_size, _BILINEAR)
    return pil_image


def _grayscale(image: str | Path | np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    pil_image = _image_to_pil(image)
    return np.asarray(pil_image.convert("L"), dtype=np.float64)


def sharpness(image) -> float:
    """Variance-of-Laplacian sharpness."""
    gray = _grayscale(image)
    if min(gray.shape) < 3:
        return 0.0

    laplacian = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - (4.0 * gray[1:-1, 1:-1])
    )
    return float(laplacian.var())


def brightness(image) -> float:
    """Mean luminance in the 0..255 range."""
    gray = _grayscale(image)
    return float(gray.mean())


def quality(image, blur_threshold=60.0, dark_threshold=12.0) -> dict:
    """Score frame quality for intake gating."""
    image_sharpness = sharpness(image)
    image_brightness = brightness(image)
    blurry = image_sharpness < float(blur_threshold)
    dark = image_brightness < float(dark_threshold)
    return {
        "sharpness": image_sharpness,
        "brightness": image_brightness,
        "blurry": blurry,
        "dark": dark,
        "keep": (not blurry) and (not dark),
    }
