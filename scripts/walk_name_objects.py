#!/usr/bin/env python3
"""Trust-tier offline walk labels with a serial gemma vision confirmation pass."""
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable


NONE_LABELS = {
    "none",
    "no",
    "no object",
    "not an object",
    "background",
    "wall",
    "floor",
    "ceiling",
    "surface",
    "texture",
    "text",
    "area",
    "image",
    "crop",
    "object",
    "thing",
}


def _load_records(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        source = raw
    elif isinstance(raw, dict):
        source = raw.get("labels") or raw.get("crops") or raw.get("objects") or []
    else:
        source = []
    return [dict(item) for item in source if isinstance(item, dict)]


def _clip_word(record: dict[str, Any]) -> str:
    return " ".join(str(record.get("word") or record.get("label") or record.get("name") or "").strip().lower().split())


def _score(record: dict[str, Any]) -> float:
    try:
        value = float(record.get("score", record.get("confidence", 0.0)))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _record_crop_path(record: dict[str, Any], crops_dir: str | None = None) -> str:
    value = record.get("crop_path") or record.get("crop") or record.get("path") or record.get("file") or ""
    path = str(value)
    if not path:
        return path
    # The stored path may already be a full (relative) path that resolves
    # from cwd — use it as-is. Only re-root under crops_dir when it does
    # not resolve, trying basename first (avoids double-prefixing a path
    # that already contains the crops dir).
    if os.path.exists(path):
        return path
    if crops_dir:
        cand = str(Path(crops_dir) / os.path.basename(path))
        if os.path.exists(cand):
            return cand
        joined = str(Path(crops_dir) / path)
        if os.path.exists(joined):
            return joined
    return path


def _clean_label(text: str) -> str | None:
    text = text.strip().lower()
    text = re.sub(r"^name\s*:\s*", "", text)
    text = re.sub(r"^(a|an|the)\s+", "", text)
    text = re.sub(r"[^a-z0-9 /-]+", " ", text)
    text = " ".join(text.split())
    if not text:
        return None
    tokens = re.split(r"[\s/-]+", text)
    if len([t for t in tokens if t]) > 3:
        return None
    if text in NONE_LABELS:
        return None
    if any(token in NONE_LABELS for token in tokens):
        return None
    return text


def parse_gemma_answer(raw: str, clip_word: str) -> tuple[str | None, str]:
    """Return (label, decision), where label None means reject."""
    text = str(raw or "").strip()
    if not text:
        return None, "empty"
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.IGNORECASE).strip()
    first_line = text.splitlines()[0].strip()
    lowered = first_line.lower()
    clip_norm = _clean_label(clip_word) or clip_word

    if re.match(r"^(yes|correct|confirmed)\b", lowered):
        return clip_norm, "confirmed"
    if lowered in NONE_LABELS or re.match(r"^(none|no distinct|not a distinct|background|no object)\b", lowered):
        return None, "none"

    name_match = re.match(r"^(?:name|label|object)\s*:\s*(.+)$", first_line, flags=re.IGNORECASE)
    if name_match:
        label = _clean_label(name_match.group(1))
        return (label, "named") if label else (None, "invalid_name")

    if clip_norm and re.search(r"\b(yes|correct|is|shows|appears)\b", lowered) and clip_norm in lowered:
        return clip_norm, "confirmed"
    if re.search(r"\b(none|background|not (?:a|an) object|no object|not distinct)\b", lowered):
        return None, "none"

    prose_match = re.search(
        r"(?:it is|it's|this is|shows|appears to be|looks like)\s+(?:a|an|the)?\s*([a-z][a-z0-9 /-]{1,45})",
        lowered,
    )
    if prose_match:
        label = _clean_label(prose_match.group(1))
        return (label, "named") if label else (None, "invalid_name")

    label = _clean_label(first_line)
    return (label, "named") if label else (None, "invalid_name")


def build_prompt(clip_word: str) -> str:
    return (
        "You are verifying one cropped image from a walking camera.\n"
        f'The CLIP candidate is "{clip_word}".\n'
        "Answer exactly one line:\n"
        f"YES if the crop clearly shows a {clip_word}.\n"
        "NAME: <1-3 plain English words> if it shows a different distinct physical object.\n"
        "NONE if it is background, a wall/floor/surface/texture, text-only, a body part, or not a distinct object.\n"
        "No prose."
    )


def ollama_responder(model: str, host: str, timeout: float) -> Callable[[dict[str, Any], str, str], str]:
    url = host.rstrip("/") + "/api/generate"

    def respond(record: dict[str, Any], crop_path: str, clip_word: str) -> str:
        from PIL import Image
        import io
        with Image.open(crop_path) as _im:
            _im = _im.convert("RGB")
            _im.thumbnail((384, 384))
            _buf = io.BytesIO()
            _im.save(_buf, format="JPEG", quality=85)
        image_b64 = base64.b64encode(_buf.getvalue()).decode("ascii")
        payload = {
            "model": model,
            "prompt": build_prompt(clip_word),
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return str(data.get("response") or "")

    return respond


def _ckpt_key(record: dict[str, Any], crops_dir: str | None, idx: int) -> str:
    return _record_crop_path(record, crops_dir) or f"idx{idx}"


def name_records(
    records: list[dict[str, Any]],
    responder: Callable[[dict[str, Any], str, str], str],
    *,
    crops_dir: str | None = None,
    score_floor: float = 0.28,
    progress_every: int = 25,
    checkpoint_path: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out: list[dict[str, Any]] = []
    gemma_calls = 0
    survivors = 0
    started = time.monotonic()
    # Resume: load any records already named in a prior (reboot-killed) run.
    done: dict[str, dict[str, Any]] = {}
    if checkpoint_path and os.path.exists(checkpoint_path):
        with open(checkpoint_path, encoding="utf-8") as cf:
            for line in cf:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                k = rec.get("_ckpt_key")
                if k:
                    done[k] = rec
        if done:
            print(f"resume: {len(done)} records loaded from checkpoint", file=sys.stderr, flush=True)
    ckpt_fh = open(checkpoint_path, "a", encoding="utf-8") if checkpoint_path else None
    for idx, record in enumerate(records, start=1):
        key = _ckpt_key(record, crops_dir, idx)
        if key in done:
            out.append(done[key])
            continue
        item = dict(record)
        clip = _clip_word(record)
        score = _score(record)
        item["clip_word"] = clip
        item["clip_score"] = score
        if not clip:
            item.update({"word": "", "label": "", "trust": "rejected", "name_source": "clip_only", "reject_reason": "missing_clip_word"})
            out.append(item)
            continue
        if score < score_floor:
            item.update({"word": clip, "label": clip, "trust": "rejected", "name_source": "clip_only", "reject_reason": "below_score_floor"})
            out.append(item)
            continue

        survivors += 1
        crop_path = _record_crop_path(record, crops_dir)
        if not crop_path or not os.path.exists(crop_path):
            item.update({"word": clip, "label": clip, "trust": "rejected", "name_source": "clip_only", "reject_reason": "missing_crop"})
            out.append(item)
            continue

        raw = responder(record, crop_path, clip)
        gemma_calls += 1
        gemma_label, decision = parse_gemma_answer(raw, clip)
        item["gemma_raw"] = raw
        item["gemma_label"] = gemma_label or "NONE"
        if gemma_label is None:
            item.update({"word": clip, "label": clip, "trust": "rejected", "name_source": "clip_only", "reject_reason": f"gemma_{decision}"})
        elif gemma_label == (_clean_label(clip) or clip):
            item.update({"word": clip, "label": clip, "trust": "trusted", "name_source": "clip_agreed"})
        else:
            item.update({"word": gemma_label, "label": gemma_label, "trust": "trusted", "name_source": "gemma_named"})
        out.append(item)
        if ckpt_fh is not None:
            item["_ckpt_key"] = key
            ckpt_fh.write(json.dumps(item) + "\n")
            ckpt_fh.flush()

        if progress_every and (idx == len(records) or gemma_calls == 1 or gemma_calls % progress_every == 0):
            elapsed = time.monotonic() - started
            print(
                f"named {idx}/{len(records)} records; gemma_calls={gemma_calls}; survivors={survivors}; elapsed={elapsed:.1f}s",
                file=sys.stderr,
                flush=True,
            )

    if ckpt_fh is not None:
        ckpt_fh.close()
    counts = Counter(str(item.get("name_source") or "") for item in out)
    trusts = Counter(str(item.get("trust") or "") for item in out)
    trusted_words = {str(item.get("word") or "") for item in out if item.get("trust") == "trusted" and item.get("word")}
    stats = {
        "records": len(records),
        "survivors": survivors,
        "gemma_calls": gemma_calls,
        "trusted_records": trusts.get("trusted", 0),
        "rejected_records": trusts.get("rejected", 0),
        "trusted_distinct": len(trusted_words),
        "name_source_counts": dict(counts),
        "elapsed_s": round(time.monotonic() - started, 3),
    }
    return out, stats


def self_test() -> int:
    records = [
        {"word": "mug", "score": 0.91, "crop_path": "/tmp/a.jpg"},
        {"word": "bedpan", "score": 0.92, "crop_path": "/tmp/b.jpg"},
        {"word": "razorblade", "score": 0.93, "crop_path": "/tmp/c.jpg"},
        {"word": "wall", "score": 0.10, "crop_path": "/tmp/d.jpg"},
    ]
    answers = {
        "mug": "YES",
        "bedpan": "NAME: cabinet",
        "razorblade": "NONE",
    }

    def responder(_record: dict[str, Any], _crop_path: str, clip_word: str) -> str:
        return answers[clip_word]

    old_exists = os.path.exists
    try:
        os.path.exists = lambda _path: True  # type: ignore[assignment]
        named, stats = name_records(records, responder, score_floor=0.28, progress_every=0)
    finally:
        os.path.exists = old_exists  # type: ignore[assignment]

    assert named[0]["trust"] == "trusted" and named[0]["word"] == "mug" and named[0]["name_source"] == "clip_agreed"
    assert named[1]["trust"] == "trusted" and named[1]["word"] == "cabinet" and named[1]["name_source"] == "gemma_named"
    assert named[2]["trust"] == "rejected" and named[2]["name_source"] == "clip_only"
    assert named[3]["trust"] == "rejected" and named[3]["reject_reason"] == "below_score_floor"
    assert stats["gemma_calls"] == 3
    assert stats["trusted_distinct"] == 2
    print("SELF-TEST PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="/tmp/walk_labels.json")
    parser.add_argument("--crops-dir", default="")
    parser.add_argument("--vocab", default="ops/spatial_vocab.txt", help="Kept for pipeline symmetry; gemma may name outside this vocab.")
    parser.add_argument("--out", default="/tmp/walk_named.json")
    parser.add_argument("--score-floor", type=float, default=0.28)
    parser.add_argument("--model", default="gemma3:12b")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--checkpoint", default="", help="NDJSON checkpoint for reboot-resume; default <out>.ckpt.ndjson")
    parser.add_argument("--shard", default="", help="i/N — process only every Nth record (offset i), for parallel runs")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    _ = args.vocab
    records = _load_records(args.labels)
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        records = [r for k, r in enumerate(records) if k % n == i]
    responder = ollama_responder(args.model, args.ollama_host, args.timeout)
    checkpoint = args.checkpoint or (args.out + ".ckpt.ndjson")
    named, stats = name_records(
        records,
        responder,
        crops_dir=args.crops_dir or None,
        score_floor=args.score_floor,
        progress_every=args.progress_every,
        checkpoint_path=checkpoint,
    )
    # strip internal key before final write
    for _it in named:
        _it.pop("_ckpt_key", None)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(named, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
