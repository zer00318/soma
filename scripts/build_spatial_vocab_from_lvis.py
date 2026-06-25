#!/usr/bin/env python3
"""Build a larger spatial vocabulary from LVIS plus the current hand vocab.

The local model does the relevance filter in small batches. The script keeps
batch output cached so an interrupted run can resume without re-asking the
model for completed batches.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LVIS = Path("/tmp/lvis.yaml")
DEFAULT_VOCAB = ROOT / "ops" / "spatial_vocab.txt"
DEFAULT_KEEP = Path("/tmp/lvis_indoor_keep.json")
DEFAULT_BATCH_CACHE = Path("/tmp/lvis_indoor_filter_batches.jsonl")
DEFAULT_OUTPUT = Path("/tmp/spatial_vocab_mega.txt")
LVIS_URL = "https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/cfg/datasets/lvis.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lvis", type=Path, default=DEFAULT_LVIS)
    parser.add_argument("--vocab", type=Path, default=DEFAULT_VOCAB)
    parser.add_argument("--keep-json", type=Path, default=DEFAULT_KEEP)
    parser.add_argument("--batch-cache", type=Path, default=DEFAULT_BATCH_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--server", default="http://127.0.0.1:1234")
    parser.add_argument("--model", default="trace-local-worker")
    parser.add_argument("--provider", choices=["lmstudio", "ollama"], default="lmstudio")
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--apply", action="store_true", help="Overwrite ops/spatial_vocab.txt with the merged vocab.")
    parser.add_argument("--no-llm", action="store_true", help="Use a broad heuristic filter instead of calling the local LLM.")
    return parser.parse_args()


def ensure_lvis(path: Path) -> None:
    if path.exists() and path.stat().st_size > 100_000:
        return
    with urllib.request.urlopen(LVIS_URL, timeout=60) as response:
        path.write_bytes(response.read())


def normalize_label(label: str) -> str:
    label = label.split("/")[0]
    label = re.sub(r"\([^)]*\)", "", label)
    label = label.replace("_", " ").replace("-", " ")
    label = re.sub(r"[^a-zA-Z0-9 +]", " ", label)
    label = re.sub(r"\s+", " ", label).strip().lower()
    return label


def read_lvis(path: Path) -> list[str]:
    labels: list[str] = []
    pattern = re.compile(r"^\s+\d+:\s*(.+?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        label = normalize_label(match.group(1))
        if label and label not in labels:
            labels.append(label)
    return labels


def read_vocab(path: Path) -> list[str]:
    words: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        word = normalize_label(raw)
        if word and not word.startswith("#") and word not in words:
            words.append(word)
    return words


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def cached_batches(path: Path) -> dict[int, list[str]]:
    cached: dict[int, list[str]] = {}
    if not path.exists():
        return cached
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            cached[int(row["batch"])] = [str(value) for value in row["keep"]]
        except (ValueError, KeyError, TypeError):
            continue
    return cached


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, flags=re.S)
    if not match:
        raise ValueError(f"No JSON object in model response: {text[:200]}")
    return json.loads(match.group(0))


def model_prompt(labels: list[str]) -> str:
    task = (
        "Filter object labels for a spatial memory prototype. Keep labels that are "
        "physical, visually recognizable, and plausible indoors, at a desk, in a home, "
        "office, shop, car, bag, or carried by a person. Include furniture, electronics, "
        "tools, containers, appliances, clothing, accessories, food, kitchen/bath items, "
        "decor, toys, instruments, sports items, and common fixtures. Exclude animals, "
        "people, body parts, places, terrain, abstract concepts, materials alone, "
        "vehicles too large for indoor/carry contexts unless commonly seen from a window, "
        "and labels that are too obscure to help a live prototype. Return ONLY JSON: "
        "{\"keep\": [labels copied exactly from the input]}."
    )
    return task + "\n\nINPUT_LABELS:\n" + json.dumps(labels, ensure_ascii=False)


def ask_lmstudio(server: str, model: str, timeout: int, labels: list[str]) -> list[str]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 1600,
        "messages": [
            {"role": "system", "content": "You are a careful taxonomy filter. Return valid JSON only."},
            {"role": "user", "content": model_prompt(labels)},
        ],
    }
    request = urllib.request.Request(
        server.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"]
    raw_keep = extract_json_object(content).get("keep", [])
    allowed = set(labels)
    return [label for label in raw_keep if isinstance(label, str) and label in allowed]


def ask_ollama(server: str, model: str, timeout: int, labels: list[str]) -> list[str]:
    payload = {
        "model": model,
        "stream": False,
        "prompt": "You are a careful taxonomy filter. Return valid JSON only.\n\n" + model_prompt(labels),
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        server.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    raw_keep = extract_json_object(result.get("response", "")).get("keep", [])
    allowed = set(labels)
    return [label for label in raw_keep if isinstance(label, str) and label in allowed]


def ask_local_model(provider: str, server: str, model: str, timeout: int, labels: list[str]) -> list[str]:
    if provider == "ollama":
        return ask_ollama(server, model, timeout, labels)
    return ask_lmstudio(server, model, timeout, labels)


def heuristic_keep(labels: list[str]) -> list[str]:
    reject_terms = {
        "baboon", "bear", "bird", "cat", "cattle", "deer", "dog", "elephant", "fish",
        "horse", "lion", "monkey", "person", "sheep", "snake", "tiger", "zebra",
        "airplane", "ambulance", "barge", "bus", "ship", "train",
    }
    kept: list[str] = []
    for label in labels:
        if any(term in label for term in reject_terms):
            continue
        if len(label) > 34:
            continue
        kept.append(label)
    return kept


def merge_vocab(base: list[str], additions: list[str]) -> list[str]:
    aliases = {
        "cellular telephone": "phone",
        "computer keyboard": "keyboard",
        "computer mouse": "mouse",
        "garbage can": "trash bin",
        "laptop computer": "laptop",
        "television receiver": "television",
    }
    merged: list[str] = []
    for word in base + additions:
        word = aliases.get(word, word)
        if not word or word in merged:
            continue
        merged.append(word)
    return sorted(merged)


def main() -> int:
    args = parse_args()
    ensure_lvis(args.lvis)
    base = read_vocab(args.vocab)
    lvis = read_lvis(args.lvis)
    batches = chunks(lvis, max(args.batch_size, 1))
    cache = cached_batches(args.batch_cache)
    args.batch_cache.parent.mkdir(parents=True, exist_ok=True)

    all_keep: list[str] = []
    with args.batch_cache.open("a", encoding="utf-8") as cache_file:
        for index, batch in enumerate(batches):
            if index in cache:
                keep = cache[index]
            elif args.no_llm:
                keep = heuristic_keep(batch)
                cache_file.write(json.dumps({"batch": index, "keep": keep}, sort_keys=True) + "\n")
                cache_file.flush()
            else:
                for attempt in range(1, 4):
                    try:
                        keep = ask_local_model(args.provider, args.server, args.model, args.timeout, batch)
                        break
                    except Exception as exc:
                        if attempt == 3:
                            raise RuntimeError(f"batch {index} failed after 3 attempts") from exc
                        time.sleep(3 * attempt)
                cache_file.write(json.dumps({"batch": index, "keep": keep}, sort_keys=True) + "\n")
                cache_file.flush()
            all_keep.extend(label for label in keep if label not in all_keep)
            print(f"batch {index + 1}/{len(batches)}: kept {len(keep)}")

    merged = merge_vocab(base, all_keep)
    args.keep_json.write_text(json.dumps(all_keep, indent=2, sort_keys=True), encoding="utf-8")
    args.output.write_text("\n".join(merged) + "\n", encoding="utf-8")
    if args.apply:
        args.vocab.write_text("\n".join(merged) + "\n", encoding="utf-8")
    print(f"base={len(base)} lvis={len(lvis)} lvis_kept={len(all_keep)} merged={len(merged)}")
    print(f"keep json: {args.keep_json}")
    print(f"vocab: {args.vocab if args.apply else args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
