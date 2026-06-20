#!/usr/bin/env python3
"""Build MobileCLIP-S0 spatial vocabulary embeddings for the iOS app.

This is an offline-only helper. It downloads/uses Apple's MobileCLIP-S0
checkpoint for the text encoder, L2-normalizes every vocab prompt embedding,
and writes a small JSON dictionary that the app can bundle. The text encoder
does not ship in the app.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOCAB = ROOT / "ops" / "spatial_vocab.txt"
DEFAULT_CHECKPOINT = ROOT / "models" / "mobileclip" / "mobileclip_s0.pt"
DEFAULT_OUTPUT = (
    ROOT
    / "soma-native-fastvlm"
    / "FastVLM App"
    / "Resources"
    / "vocab_embeddings.json"
)
DEFAULT_IMAGE_MODEL_DIR = ROOT / "soma-native-fastvlm" / "FastVLM App"
APPLE_S0_CHECKPOINT_URL = (
    "https://docs-assets.developer.apple.com/ml-research/datasets/mobileclip/mobileclip_s0.pt"
)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ensure_checkpoint(path: Path) -> None:
    if path.exists() and path.stat().st_size > 200_000_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "curl",
            "-L",
            "-C",
            "-",
            "--retry",
            "5",
            "--retry-delay",
            "2",
            APPLE_S0_CHECKPOINT_URL,
            "-o",
            str(path),
        ]
    )


def ensure_coreml_image_model(destination: Path) -> None:
    model_dir = destination / "mobileclip_s0_image.mlpackage"
    manifest = model_dir / "Manifest.json"
    if manifest.exists():
        return
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required to fetch the Core ML image model. "
            "Install it in .venv or copy mobileclip_s0_image.mlpackage manually."
        ) from exc

    snapshot_download(
        repo_id="apple/coreml-mobileclip",
        allow_patterns=["mobileclip_s0_image.mlpackage/*"],
        local_dir=str(destination),
    )


def read_vocab(path: Path) -> list[str]:
    words: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        word = raw.strip().lower()
        if not word or word.startswith("#"):
            continue
        if word not in words:
            words.append(word)
    return words


def prompt_for(word: str) -> str:
    article = "an" if word[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"a photo of {article} {word}"


def normalize(values: Iterable[float]) -> list[float]:
    vector = [float(v) for v in values]
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise ValueError("zero vector from text encoder")
    return [v / norm for v in vector]


def build_embeddings(words: list[str], checkpoint: Path) -> dict[str, list[float]]:
    try:
        import mobileclip
        import torch
    except ImportError as exc:
        raise SystemExit(
            "mobileclip and torch are required. Run: "
            ".venv/bin/python -m pip install git+https://github.com/apple/ml-mobileclip.git"
        ) from exc

    model, _, _ = mobileclip.create_model_and_transforms(
        "mobileclip_s0",
        pretrained=str(checkpoint),
        device="cpu",
    )
    model.eval()
    tokenizer = mobileclip.get_tokenizer("mobileclip_s0")
    prompts = [prompt_for(word) for word in words]
    tokens = tokenizer(prompts)
    embeddings: dict[str, list[float]] = {}
    with torch.no_grad():
        text_features = model.encode_text(tokens)
        text_features = text_features.detach().cpu()
    for word, embedding in zip(words, text_features):
        embeddings[word] = normalize(embedding.tolist())
    return embeddings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--image-model-dir", type=Path, default=DEFAULT_IMAGE_MODEL_DIR)
    parser.add_argument(
        "--skip-image-model",
        action="store_true",
        help="Only write vocab_embeddings.json; do not fetch the Core ML image package.",
    )
    args = parser.parse_args()

    ensure_checkpoint(args.checkpoint)
    if not args.skip_image_model:
        ensure_coreml_image_model(args.image_model_dir)

    words = read_vocab(args.vocab)
    if not words:
        raise SystemExit(f"No vocabulary words found in {args.vocab}")

    embeddings = build_embeddings(words, args.checkpoint)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": "mobileclip_s0",
        "prompt": "a photo of a/an {word}",
        "dimensions": 512,
        "words": embeddings,
    }
    args.output.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(embeddings)} embeddings to {args.output}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    raise SystemExit(main())
