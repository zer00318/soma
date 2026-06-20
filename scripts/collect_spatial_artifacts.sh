#!/usr/bin/env bash
set -euo pipefail

DEVICE_ID="${SOMA_DEVICE_ID:-D3A506B2-8923-5313-B8A3-FF769ABBA228}"
BUNDLE_ID="${SOMA_BUNDLE_ID:-de.zer00.soma}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${1:-/tmp/spatial_pull/${STAMP}}"

mkdir -p "$OUT_DIR"

echo "Collecting spatial artifacts into $OUT_DIR"
echo "device=$DEVICE_ID bundle=$BUNDLE_ID" > "$OUT_DIR/collector_meta.txt"
date -u +"collected_at=%Y-%m-%dT%H:%M:%SZ" >> "$OUT_DIR/collector_meta.txt"
git -C "$ROOT" rev-parse --short HEAD | sed 's/^/repo_sha=/' >> "$OUT_DIR/collector_meta.txt"

pull_app_file() {
  local source_path="$1"
  local dest_name="$2"
  local dest_path="$OUT_DIR/$dest_name"
  local log_path="$OUT_DIR/${dest_name}.copy.log"

  rm -rf "$dest_path" "$log_path"
  if xcrun devicectl device copy from \
      --device "$DEVICE_ID" \
      --domain-type appDataContainer \
      --domain-identifier "$BUNDLE_ID" \
      --source "$source_path" \
      --destination "$dest_path" >"$log_path" 2>&1; then
    if [[ -f "$dest_path" ]]; then
      local bytes
      bytes="$(wc -c < "$dest_path" | tr -d ' ')"
      echo "pulled $dest_name ($bytes bytes)"
    else
      echo "pulled $dest_name"
    fi
  else
    echo "missing $dest_name (see $log_path)"
  fi
}

pull_app_file "Library/Application Support/SOMA/spatial_world.json" "spatial_world.json"
pull_app_file "Library/Application Support/SOMA/spatial_diag.ndjson" "spatial_diag.ndjson"
pull_app_file "Library/Application Support/SOMA/vocab_misses.ndjson" "vocab_misses.ndjson"
pull_app_file "Library/Application Support/SOMA/perception_spool.ndjson" "perception_spool.ndjson"
pull_app_file "Library/Application Support/SOMA/spatial_world.arexperience" "spatial_world.arexperience"

if curl -fsS "http://127.0.0.1:8777/api/world" -o "$OUT_DIR/world.json"; then
  echo "pulled dashboard world.json"
else
  echo "dashboard /api/world unavailable"
fi

if [[ -s "$OUT_DIR/spatial_diag.ndjson" ]]; then
  python3 "$ROOT/scripts/analyze_spatial_diag.py" "$OUT_DIR/spatial_diag.ndjson" \
    | tee "$OUT_DIR/spatial_diag_report.txt"
else
  echo "spatial_diag.ndjson is empty or missing; no diagnostic report yet"
fi

if [[ -s "$OUT_DIR/vocab_misses.ndjson" ]]; then
  python3 - "$OUT_DIR/vocab_misses.ndjson" <<'PY' | tee "$OUT_DIR/vocab_misses_report.txt"
from __future__ import annotations
import collections
import json
import statistics
import sys

path = sys.argv[1]
rows = []
bad = 0
with open(path, "r", encoding="utf-8") as handle:
    for line in handle:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1

by_word = collections.Counter(str(row.get("best_word", "")).strip() or "__unknown__" for row in rows)
scores = [float(row["score"]) for row in rows if isinstance(row.get("score"), (int, float))]
margins = [float(row["margin"]) for row in rows if isinstance(row.get("margin"), (int, float))]

def pct(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(percentile * (len(ordered) - 1))
    return round(ordered[index], 3)

print(f"Total vocab misses: {len(rows)}")
print(f"Bad lines: {bad}")
print(f"Score p50/p95: {round(statistics.median(scores), 3) if scores else None} / {pct(scores, 0.95)}")
print(f"Margin p50/p95: {round(statistics.median(margins), 3) if margins else None} / {pct(margins, 0.95)}")
print("Top rejected best words:")
for word, count in by_word.most_common(20):
    print(f"{word}: {count}")
PY
else
  echo "vocab_misses.ndjson is empty or missing; no vocab report yet"
fi

echo "$OUT_DIR" > /tmp/soma_latest_spatial_pull.txt
echo "latest pull marker: /tmp/soma_latest_spatial_pull.txt"
echo "done"
