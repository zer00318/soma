from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import re
import sys
import tempfile
import urllib.request
import time
from typing import Callable, Set, Dict, List, Tuple

def describe_photo(path: str, describer: Callable[[str], Set[str]] = None) -> Set[str]:
    if describer is not None:
        return describer(path)
    
    try:
        with open(path, 'rb') as f:
            image_data = f.read()
    except Exception as e:
        print(f"Error reading {path}: {e}", file=sys.stderr)
        return set()

    # Handle HEIC by passing raw bytes
    if path.lower().endswith('.heic'):
        image_b64 = base64.b64encode(image_data).decode('utf-8')
    else:
        image_b64 = base64.b64encode(image_data).decode('utf-8')

    payload = {
        "model": "gemma3:12b-it-qat",
        "prompt": "List every distinct solid object you can clearly see in this room photo. Comma-separated short lowercase noun phrases only (e.g. desk, keyboard, office chair). No guessing, no colors, no sentences.",
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0}
    }

    req = urllib.request.Request(
        url="http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            text = result.get("response", "").strip()
    except Exception as e:
        print(f"Error calling Ollama for {path}: {e}", file=sys.stderr)
        return set()

    words = re.split(r'[,;\n]+', text)
    words = [w.strip().lower() for w in words]
    words = [w for w in words if w and len(w.split()) <= 4]

    return set(words)

def world_labels(api_url: str = 'http://127.0.0.1:8777/api/world', token: str = 'dev-token') -> Dict[str, Dict]:
    req = urllib.request.Request(
        url=api_url,
        headers={"X-TRACE-Token": token},
        method="GET"
    )

    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching world labels: {e}", file=sys.stderr)
        return {}

    result = {}
    for obj in data.get("objects", []):
        if not isinstance(obj, dict) or obj.get("phantom") is True:
            continue
        label = str(obj.get("label", "")).strip().lower()
        if label:
            result[label] = obj

    return result

def match(a: str, b: str) -> bool:
    a_tokens = set(a.split())
    b_tokens = set(b.split())

    # Check for shared tokens of length >= 4
    common_long = a_tokens & {t for t in b_tokens if len(t) >= 4}
    if common_long:
        return True

    # Check containment
    if a in b or b in a:
        return True

    return False

def score(photo_objects: Set[str], world: Dict[str, Dict]) -> Dict:
    matched = []
    unsupported = []
    captured = []
    missed = []

    photo_list = list(photo_objects)
    world_labels = list(world.keys())

    for label in world_labels:
        found = False
        for photo_word in photo_list:
            if match(label, photo_word):
                matched.append(label)
                found = True
                break
        if not found:
            unsupported.append(label)

    for word in photo_list:
        found = any(match(word, label) for label in world_labels)
        if found:
            captured.append(word)
        else:
            missed.append(word)

    precision = 0.0
    recall = 0.0

    if matched or unsupported:
        precision = round(len(matched) / (len(matched) + len(unsupported)), 3)
    if captured or missed:
        recall = round(len(captured) / (len(captured) + len(missed)), 3)

    return {
        "precision": precision,
        "recall": recall,
        "matched": sorted(matched),
        "phantom_suspects": sorted(unsupported),
        "missed": sorted(missed)
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--photos', default='data/gt_photos')
    parser.add_argument('--out', default='/tmp/gt_room_report.md')
    parser.add_argument('--api', action='store_true')
    parser.add_argument('--self-test', action='store_true')

    args = parser.parse_args()

    if args.self_test:
        def stub_describer(path):
            return {'desk','keyboard','window','office chair'}

        def stub_world():
            return {'keyboard':{},'iron board':{},'desk':{},'monitor':{}}

        result = score(
            photo_objects={'desk','keyboard','window','office chair'},
            world=stub_world()
        )

        assert result['precision'] == 0.5
        assert 'iron board' in result['phantom_suspects']
        print('SELF-TEST PASS')
        sys.exit(0)

    if not os.path.isdir(args.photos):
        print(f"Photos directory {args.photos} does not exist", file=sys.stderr)
        sys.exit(1)

    all_photo_objects = set()
    photo_files = []

    for fname in os.listdir(args.photos):
        if re.match(r'.*\.(jpg|jpeg|png|heic)$', fname, re.IGNORECASE):
            path = os.path.join(args.photos, fname)
            photo_files.append(path)

    for path in photo_files:
        try:
            words = describe_photo(path)
            all_photo_objects.update(words)
        except Exception as e:
            print(f"Warning: failed to process {path}: {e}", file=sys.stderr)

    if not args.api:
        world = {}
    else:
        world = world_labels()

    result = score(all_photo_objects, world)

    md_lines = []
    md_lines.append(f"# Room Photo Evaluation Report\n")
    md_lines.append(f"Precision: {result['precision']}\n")
    md_lines.append(f"Recall: {result['recall']}\n")

    md_lines.append("## Matched Objects\n")
    for obj in result['matched']:
        md_lines.append(f"- {obj}")

    md_lines.append("\n## Phantom Suspects (Unsupported)\n")
    for obj in result['phantom_suspects']:
        md_lines.append(f"- {obj}")

    md_lines.append("\n## Missed Objects\n")
    for obj in result['missed']:
        md_lines.append(f"- {obj}")

    md_lines.append("\n## Per-Photo Object Lists\n")
    for path in photo_files:
        words = describe_photo(path)
        md_lines.append(f"### {os.path.basename(path)}\n")
        md_lines.append("- " + "\n- ".join(sorted(words)) + "\n")

    with open(args.out, 'w') as f:
        f.write('\n'.join(md_lines))

    print(f"Report written to {args.out}")
    print(f"Precision: {result['precision']}, Recall: {result['recall']}")

if __name__ == '__main__':
    main()
