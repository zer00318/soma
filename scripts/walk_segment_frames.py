from __future__ import annotations

import argparse
import os
import sys
import json
import cv2
import numpy as np
from pathlib import Path
import tempfile
import shutil


def run_fastsam(frame_paths, model_name='FastSAM-s.pt', conf=0.4, iou=0.9):
    # Lazy import
    from ultralytics import FastSAM

    model = FastSAM(model_name)
    result_dict = {}

    for frame_path in frame_paths:
        results = model(
            frame_path,
            device='mps',
            retina_masks=False,
            imgsz=1024,
            conf=conf,
            iou=iou
        )
        boxes = []
        if results[0].boxes is not None:
            for box in results[0].boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                boxes.append([int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])])
        result_dict[frame_path] = boxes

    return result_dict


def filter_boxes(boxes, frame_w, frame_h, min_frac=0.0015, max_frac=0.6):
    def area(box):
        return (box[2] - box[0]) * (box[3] - box[1])

    def iou(box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        if x1 >= x2 or y1 >= y2:
            return 0.0
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        return intersection / (area1 + area2 - intersection)

    # Filter by area fraction
    frame_area = frame_w * frame_h
    filtered_boxes = []
    for box in boxes:
        box_area = area(box)
        frac = box_area / frame_area
        if min_frac <= frac <= max_frac:
            filtered_boxes.append(box)

    # Deduplicate using IoU > 0.85, keeping larger ones
    kept = []
    for box in filtered_boxes:
        is_duplicate = False
        for kept_box in kept:
            if iou(box, kept_box) > 0.85:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(box)

    # Among overlapping boxes, keep the larger one
    final_boxes = []
    for box in kept:
        is_larger = True
        for other_box in kept:
            if other_box != box and iou(box, other_box) > 0.85:
                if area(box) < area(other_box):
                    is_larger = False
                    break
        if is_larger:
            final_boxes.append(box)

    return final_boxes


def save_crops(frame_path, boxes, out_dir, pad=0.06):
    frame = cv2.imread(frame_path)
    h, w = frame.shape[:2]
    crop_dicts = []

    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        # Expand by pad fraction
        pad_w = int((x2 - x1) * pad)
        pad_h = int((y2 - y1) * pad)
        x1 = max(0, x1 - pad_w)
        y1 = max(0, y1 - pad_h)
        x2 = min(w, x2 + pad_w)
        y2 = min(h, y2 + pad_h)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        base = os.path.splitext(os.path.basename(frame_path))[0]
        crop_filename = f"{base}_obj{i}.jpg"
        crop_path = os.path.join(out_dir, crop_filename)
        cv2.imwrite(crop_path, crop)

        crop_dicts.append({
            'crop': crop_path,
            'frame': frame_path,
            'box': [x1, y1, x2, y2]
        })

    return crop_dicts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames-dir', default='/tmp/walk_frames')
    parser.add_argument('--out', default='/tmp/walk_crops')
    parser.add_argument('--limit-frames', type=int, default=0)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        # Create a temporary image with known structure
        temp_dir = tempfile.mkdtemp()
        test_img_path = os.path.join(temp_dir, 'test.jpg')
        img = np.ones((200, 200, 3), dtype=np.uint8) * 255
        cv2.rectangle(img, (20, 20), (80, 80), (0, 0, 0), -1)
        cv2.imwrite(test_img_path, img)

        boxes = [[20, 20, 80, 80], [21, 21, 81, 81], [0, 0, 199, 199], [2, 2, 4, 4]]
        filtered = filter_boxes(boxes, 200, 200)
        assert len(filtered) == 1
        assert filtered[0] == [20, 20, 80, 80]

        # Test save_crops
        crop_dir = os.path.join(temp_dir, 'crops')
        os.makedirs(crop_dir, exist_ok=True)
        crops = save_crops(test_img_path, filtered, crop_dir)
        assert len(crops) == 1
        crop_path = crops[0]['crop']
        assert os.path.exists(crop_path)
        crop_img = cv2.imread(crop_path)
        assert crop_img.shape[0] > 0 and crop_img.shape[1] > 0

        shutil.rmtree(temp_dir)
        print("SELF-TEST PASS")
        sys.exit(0)

    frames_dir = args.frames_dir
    out_dir = args.out
    limit_frames = args.limit_frames

    os.makedirs(out_dir, exist_ok=True)

    # Read manifest or glob jpgs
    manifest_path = os.path.join(frames_dir, 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest_entries = json.load(f)
        frame_paths = [
            os.path.join(frames_dir, m['file']) if isinstance(m, dict) else str(m)
            for m in manifest_entries
        ]
    else:
        frame_paths = [str(p) for p in Path(frames_dir).glob('*.jpg')]

    if limit_frames > 0:
        frame_paths = frame_paths[:limit_frames]

    # Process in batches
    batch_size = 16
    all_crops = []

    for i in range(0, len(frame_paths), batch_size):
        batch_paths = frame_paths[i:i+batch_size]
        results = run_fastsam(batch_paths)
        for path in batch_paths:
            boxes = results[path]
            if not boxes:
                continue
            # Get image dimensions
            img = cv2.imread(path)
            h, w = img.shape[:2]
            filtered_boxes = filter_boxes(boxes, w, h)
            crops = save_crops(path, filtered_boxes, out_dir)
            all_crops.extend(crops)

    # Write manifest
    manifest_path = os.path.join(out_dir, 'crops_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(all_crops, f)

    print(f"Total crops saved: {len(all_crops)}")


if __name__ == '__main__':
    main()
