from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageFilter

from scripts.frame_quality import brightness, quality, sharpness


try:
    _NEAREST = Image.Resampling.NEAREST
except AttributeError:  # Pillow < 9.1
    _NEAREST = Image.NEAREST


def _checkerboard(size: int, block: int = 8) -> np.ndarray:
    y, x = np.indices((size, size))
    pattern = (((x // block) + (y // block)) % 2 * 255).astype(np.uint8)
    return np.repeat(pattern[:, :, None], 3, axis=2)


def _blurred(array: np.ndarray, radius: float = 4.0) -> np.ndarray:
    image = Image.fromarray(array, mode="RGB")
    return np.asarray(image.filter(ImageFilter.GaussianBlur(radius=radius)), dtype=np.uint8)


def test_sharp_image_has_higher_sharpness_than_blurred_copy():
    sharp = _checkerboard(256, block=8)
    blurred = _blurred(sharp, radius=4.0)

    sharp_score = sharpness(sharp)
    blurred_score = sharpness(blurred)

    assert sharp_score > blurred_score


def test_quality_marks_blurred_frames_for_rejection():
    sharp = _checkerboard(256, block=8)
    blurred = _blurred(sharp, radius=4.0)

    sharp_quality = quality(sharp)
    blurred_quality = quality(blurred)

    assert sharp_quality["blurry"] is False
    assert sharp_quality["keep"] is True
    assert blurred_quality["blurry"] is True
    assert blurred_quality["keep"] is False
    assert sharp_quality["sharpness"] > blurred_quality["sharpness"]


def test_near_black_frame_is_dark_and_rejected():
    dark = np.zeros((128, 128, 3), dtype=np.uint8)

    result = quality(dark)

    assert result["dark"] is True
    assert result["keep"] is False


def test_sharpness_accepts_numpy_arrays_and_paths(tmp_path):
    image = _checkerboard(192, block=6)
    path = tmp_path / "checker.png"
    Image.fromarray(image, mode="RGB").save(path)

    assert sharpness(path) == pytest.approx(sharpness(image), rel=0.0, abs=1e-6)


def test_brightness_matches_extremes():
    white = np.full((64, 64, 3), 255, dtype=np.uint8)
    black = np.zeros((64, 64, 3), dtype=np.uint8)

    assert brightness(white) == pytest.approx(255.0, rel=0.0, abs=1e-6)
    assert brightness(black) == pytest.approx(0.0, rel=0.0, abs=1e-6)


def test_downscaling_keeps_large_sharp_images_well_above_blur_threshold():
    large = _checkerboard(1024, block=16)
    upscaled = np.asarray(
        Image.fromarray(large, mode="RGB").resize((2048, 2048), _NEAREST),
        dtype=np.uint8,
    )

    large_score = sharpness(large)
    upscaled_score = sharpness(upscaled)

    assert large_score > 60.0
    assert upscaled_score > 60.0
    ratio = max(large_score, upscaled_score) / min(large_score, upscaled_score)
    assert ratio < 10.0
