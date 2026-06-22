#!/usr/bin/env python3
"""Run Apple Vision OCR on an image."""

import argparse
from pathlib import Path

import Quartz
import Vision
from Foundation import NSURL


def ocr_cgimage(image):
    """Return text recognized in a CGImage, ordered top-to-bottom.

    In-memory only: takes a CGImage directly, never touches disk. This is the
    high-confidence verbatim-text channel for the live capture spine.
    """
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
    succeeded, error = handler.performRequests_error_([request], None)
    if not succeeded:
        raise RuntimeError(f"Vision OCR failed: {error}")

    observations = sorted(
        request.results() or [],
        key=lambda o: (-o.boundingBox().origin.y, o.boundingBox().origin.x),
    )
    lines = []
    for o in observations:
        candidates = o.topCandidates_(1)
        if candidates:
            lines.append(str(candidates[0].string()))
    return lines


def ocr_image(path):
    """Return text recognized in *path*, ordered from top to bottom."""
    image_path = Path(path).expanduser().resolve()
    url = NSURL.fileURLWithPath_(str(image_path))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        raise ValueError(f"Could not open image: {image_path}")
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if image is None:
        raise ValueError(f"Could not decode image: {image_path}")
    return ocr_cgimage(image)


def main():
    parser = argparse.ArgumentParser(description="Recognize text with Apple Vision")
    parser.add_argument("image", help="path to an image")
    args = parser.parse_args()
    print(*ocr_image(args.image), sep="\n")


if __name__ == "__main__":
    main()
