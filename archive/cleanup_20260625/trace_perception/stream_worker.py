from __future__ import annotations

import argparse
import json
import struct
import sys

import cv2
import numpy as np

from trace_perception.worker import PerceptionWorker


def read_exact(size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sys.stdin.buffer.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read length-prefixed JPEG frames from stdin and emit TRACE perception JSON."
    )
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--confidence", type=float, default=0.35)
    args = parser.parse_args(argv)

    worker = PerceptionWorker(
        camera_index=0,
        model_name=args.model,
        frame_stride=1,
        confidence=args.confidence,
    )
    print(json.dumps({"type": "detector_ready"}), flush=True)

    while True:
        header = read_exact(4)
        if header is None:
            return 0

        (size,) = struct.unpack(">I", header)
        if size == 0:
            return 0

        payload = read_exact(size)
        if payload is None:
            return 0

        encoded = np.frombuffer(payload, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None:
            print(json.dumps({"type": "error", "message": "Could not decode frame"}), flush=True)
            continue

        worker._process_frame(frame)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
