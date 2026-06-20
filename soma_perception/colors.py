from __future__ import annotations

import numpy as np


COLOR_NAMES = [
    ("black", np.array([20, 20, 20])),
    ("white", np.array([235, 235, 235])),
    ("gray", np.array([128, 128, 128])),
    ("red", np.array([200, 45, 45])),
    ("orange", np.array([230, 130, 45])),
    ("yellow", np.array([230, 210, 60])),
    ("green", np.array([55, 150, 75])),
    ("blue", np.array([65, 110, 210])),
    ("purple", np.array([135, 80, 180])),
    ("brown", np.array([120, 80, 50])),
]


def dominant_color_name(frame: np.ndarray, bbox_xyxy: tuple[float, float, float, float]) -> str:
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    x1 = max(0, min(width - 1, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height - 1, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1 or y2 <= y1:
        return "unknown"

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return "unknown"

    # OpenCV frames are BGR. Convert to RGB before comparing simple color prototypes.
    rgb = crop[:, :, ::-1].reshape(-1, 3)
    if len(rgb) > 5000:
        sample = rgb[np.linspace(0, len(rgb) - 1, 5000).astype(int)]
    else:
        sample = rgb
    median = np.median(sample, axis=0)

    label, _ = min(
        COLOR_NAMES,
        key=lambda item: float(np.linalg.norm(median - item[1])),
    )
    return label

