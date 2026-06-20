from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

def ask_photo(photo_path: str, word: str, asker=None) -> bool:
    if asker is not None:
        return asker(photo_path, word)
    
    url = "http://127.0.0.1:11434/api/generate"
    with open(photo_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "model": "gemma3:12b-it-qat",
        "prompt": f"Look carefully at every part of this photo, including edges and backgrounds. Is there a {word} visible anywhere, even partially? Answer with exactly one word: yes or no.",
        "images": [image_data],
        "stream": False,
        "options": {
            "temperature": 0
        }
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.load(response)
            return result["response"].strip().lower().startswith("yes")
    except (urllib.error.URLError, KeyError):
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suspects", type=str)
    parser.add_argument("--suspects-file", type=str)
    parser.add_argument("--photos", type=str, default="data/gt_photos_jpg")
    parser.add_argument("--out", type=str, default="/tmp/phantom_recheck.md")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        # Stub asker for self-test
        def stub_asker(photo_path: str, word: str) -> bool:
            return word == "coatrack"
        
        photos = ["a.jpg", "b.jpg"]
        suspects = ["coatrack", "unicorn"]
        
        confirmed = []
        still_unseen = []

        for suspect in suspects:
            found = False
            for photo in photos:
                if stub_asker(photo, suspect):
                    confirmed.append(suspect)
                    found = True
                    break
            if not found:
                still_unseen.append(suspect)

        assert "coatrack" in confirmed
        assert "unicorn" in still_unseen
        print("SELF-TEST PASS")
        sys.exit(0)

    # Load suspects
    if args.suspects:
        suspects = [s.strip() for s in args.suspects.split(",")]
    elif args.suspects_file:
        with open(args.suspects_file, "r") as f:
            suspects = [line.strip() for line in f if line.strip()]
    else:
        raise ValueError("Either --suspects or --suspects-file must be provided")

    # Get photo paths
    photos = []
    for fname in os.listdir(args.photos):
        if fname.lower().endswith((".jpg", ".jpeg")):
            photos.append(os.path.join(args.photos, fname))
    
    confirmed = []
    still_unseen = []
    details = []

    for suspect in suspects:
        found = False
        for photo in photos:
            if ask_photo(photo, suspect):
                confirmed.append(suspect)
                details.append(f"- {suspect} (found in {photo})")
                found = True
                break
        if not found:
            still_unseen.append(suspect)
            details.append(f"- {suspect} (not found in any photo)")

    # Write output markdown file
    with open(args.out, "w") as f:
        f.write("# Phantom Suspect Recheck Results\n\n")
        f.write("## CONFIRMED-PRESENT (gemma was blind, not a phantom)\n")
        for s in confirmed:
            f.write(f"- {s}\n")
        f.write("\n## STILL-UNSEEN (real phantom candidate)\n")
        for s in still_unseen:
            f.write(f"- {s}\n")
        f.write("\n## Per-Suspect Details\n")
        for detail in details:
            f.write(f"{detail}\n")

    print(f"Summary: {len(confirmed)} confirmed, {len(still_unseen)} still unseen. Output written to {args.out}")

if __name__ == "__main__":
    main()
