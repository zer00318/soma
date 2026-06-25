#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
python3 -m unittest discover -s tests
python3 -m compileall trace_hub
python3 -m compileall trace_perception
python3 -m trace_hub evaluate
swiftc -typecheck scripts/live_asr_macos.swift
