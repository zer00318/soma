from __future__ import annotations

import cv2
import argparse
import os
import sys
import json
import tempfile
import shutil
import numpy as np


def frame_sharpness(gray_img):
    # Compute the Laplacian of the image and return the variance
    return cv2.Laplacian(gray_img, cv2.CV_64F).var()


def extract(video_path, out_dir, fps=2.0, min_sharpness=40.0):
    # Create output directory if it doesn't exist
    os.makedirs(out_dir, exist_ok=True)

    # Open video capture
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video file: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if src_fps == 0:
        src_fps = 30.0

    step = max(1, int(src_fps / fps))

    manifest = []
    frame_index = 0
    saved_frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Only process every `step`-th frame
        if frame_index % step != 0:
            frame_index += 1
            continue

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Compute sharpness
        sharpness = frame_sharpness(gray)

        # Skip frames below minimum sharpness
        if sharpness < min_sharpness:
            frame_index += 1
            continue

        # Save the frame
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0  # time in seconds
        filename = f"frame_{frame_index:06d}_{t:.1f}s.jpg"
        filepath = os.path.join(out_dir, filename)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 88])

        # Add to manifest
        manifest.append({
            "file": filename,
            "t": t,
            "sharpness": sharpness
        })

        saved_frame_count += 1
        frame_index += 1

    cap.release()

    # Write manifest to file
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', default='', help='Input video path')
    parser.add_argument('--out', default='/tmp/walk_frames', help='Output directory')
    parser.add_argument('--fps', type=float, default=2.0, help='Output frame rate')
    parser.add_argument('--min-sharpness', type=float, default=40.0, help='Minimum sharpness threshold')
    parser.add_argument('--self-test', action='store_true', help='Run self-test')

    args = parser.parse_args()

    if args.self_test:
        # Create a temporary directory for the test
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, "test_video.mp4")
            
            # Create a 60-frame test video: 30 black frames + 30 noisy frames
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_path, fourcc, 30.0, (320, 240), isColor=False)

            # Black frames (low sharpness)
            for _ in range(30):
                frame = np.zeros((240, 320), dtype=np.uint8)
                out.write(frame)

            # Noisy frames (high sharpness)
            for _ in range(30):
                frame = np.random.randint(0, 255, (240, 320), dtype=np.uint8)
                out.write(frame)

            out.release()

            # Run extract with fps=5
            manifest = extract(video_path, temp_dir, fps=5.0, min_sharpness=40.0)

            # Assertions
            assert len(manifest) > 0, "Manifest should not be empty"
            for entry in manifest:
                assert entry["sharpness"] >= 40.0, f"Frame {entry['file']} has sharpness below threshold"

            # Count how many black frames survived (should be very few)
            black_frames = 0
            for entry in manifest:
                if entry["sharpness"] < 100:  # arbitrary low threshold
                    black_frames += 1

            assert black_frames < 8, f"Too many black frames survived: {black_frames}"

            print("SELF-TEST PASS")
            sys.exit(0)

    else:
        if not args.video:
            parser.error('--video required')
        manifest = extract(args.video, args.out, args.fps, args.min_sharpness)
        print(f"Extracted {len(manifest)} frames to {args.out}")


if __name__ == '__main__':
    main()
