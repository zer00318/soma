#!/usr/bin/env python3
"""Stable identities for rebuildable post-capture jobs.

Checkpoints from a different raw session, model prompt, selection, or job version
must never be resumed into the current artifact.
"""
from __future__ import annotations

import hashlib
import json
import os

from artifact_provenance import raw_source_sha256


def job_run_id(memory_dir, job_name, version, model, prompt, params, selected_frames):
    frame_names = [os.path.basename(path) for path in selected_frames]
    payload = {
        "raw_source_sha256": raw_source_sha256(memory_dir) or "unlinked",
        "job": job_name,
        "version": version,
        "model": model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "params": params,
        "selected_frames": frame_names,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_rows(path, run_id):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path) as source:
        for line in source:
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(row, dict) and row.get("_run_id") == run_id and row.get("frame"):
                rows[row["frame"]] = row
    return rows
