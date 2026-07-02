#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import time
import urllib.request
from pathlib import Path


def ask_ollama(prompt: str, image_paths: list[Path], model: str, timeout: int) -> str:
    images = [base64.b64encode(path.read_bytes()).decode() for path in image_paths]
    body = {
        "model": model,
        "prompt": prompt,
        "images": images,
        "stream": False,
        "options": {"temperature": 0},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))["response"].strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Run local Gemma vision against a capture-question spec.")
    ap.add_argument("spec", help="JSON file with {base_dir, questions:[{id,prompt,frames[]}...]}")
    ap.add_argument("--out", required=True, help="Path to write answers JSON")
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    ap.add_argument("--timeout", type=int, default=240)
    args = ap.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text())
    base_dir = Path(spec["base_dir"]).resolve()
    out_path = Path(args.out).resolve()
    answers = {}

    for question in spec["questions"]:
        qid = question["id"]
        image_paths = [base_dir / rel for rel in question["frames"]]
        t0 = time.time()
        try:
            answer = ask_ollama(question["prompt"], image_paths, args.model, args.timeout)
        except Exception as exc:  # noqa: BLE001
            answer = f"ERROR: {exc}"
        answers[qid] = {
            "prompt": question["prompt"],
            "frames": question["frames"],
            "answer": answer,
            "seconds": round(time.time() - t0, 2),
        }
        out_path.write_text(json.dumps(answers, indent=2))
        print(f"{qid} [{answers[qid]['seconds']}s] {answer}".replace("\n", " "), flush=True)

    print(f"WROTE {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
