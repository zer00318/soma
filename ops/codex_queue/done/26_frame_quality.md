# CODEX BRIEF 26 — frame quality / blur scorer (the intake gate)

Branch: `codex/26-frame-quality`. Python via `.venv/bin/python` (numpy + Pillow available).
Create ONE new module `scripts/frame_quality.py` + tests `tests/test_frame_quality.py`. Do NOT edit
other files.

## Why
The intake must DISCARD blurry frames so the VLM only sees sharp ones (the soya clip failed partly
because most frames were motion-blurred). This module scores frame sharpness; the brain uses it as a
Mac-side backstop and the logic is mirrored on-device. Pure, deterministic, image-in → score-out.

## The module: `scripts/frame_quality.py`

```python
def sharpness(image) -> float:
    """Variance-of-Laplacian sharpness. `image` is a path (str/Path) OR a numpy HxW(xC) array.
    Convert to grayscale, apply a 3x3 Laplacian ([[0,1,0],[1,-4,1],[0,1,0]]), return the VARIANCE
    of the result. Higher = sharper. Downscale large images to a max side of ~512 first for speed
    and scale-invariance."""

def brightness(image) -> float:
    """Mean luminance 0..255 (so we can also drop near-black frames)."""

def quality(image, blur_threshold=60.0, dark_threshold=12.0) -> dict:
    """Return {"sharpness": float, "brightness": float, "blurry": bool, "dark": bool, "keep": bool}.
    keep = (not blurry) and (not dark). blurry = sharpness < blur_threshold; dark = brightness < dark_threshold."""
```

## Acceptance tests (`tests/test_frame_quality.py`)
Build fixtures IN-CODE with numpy/PIL (no external files):
1. A high-frequency image (e.g. a random-noise or checkerboard array) has HIGHER sharpness than the
   same image after a Gaussian blur (PIL ImageFilter.GaussianBlur radius 4). Assert strict ordering.
2. quality() marks the blurred one blurry=True/keep=False when it falls below threshold and the sharp
   one blurry=False/keep=True (pick fixtures so the default threshold separates them; you may assert
   relative ordering rather than the absolute threshold if needed).
3. A near-black array (all zeros) -> dark=True, keep=False.
4. sharpness accepts both a numpy array and a written-out PNG path (same value within tolerance).
5. brightness of an all-255 array ≈ 255; all-0 ≈ 0.
6. Downscaling: a large sharp image and its 2x-upscaled copy give similar sharpness order of magnitude
   (scale-robust) — just assert both are well above the blur threshold.

## Guardrails
- Pure, deterministic, no network/LLM. numpy + Pillow only. `pytest tests/ -q` green. Commit on branch.
  Report the sharp-vs-blurred sharpness numbers from test 1.
