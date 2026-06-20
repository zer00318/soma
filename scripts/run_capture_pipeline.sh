#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-.venv/bin/python}"
capture_dir=""
out_prefix="/tmp/run"
floor="0.30"

usage() {
  cat <<'USAGE'
Usage: scripts/run_capture_pipeline.sh --capture-dir DIR [--out-prefix /tmp/run] [--floor 0.30]

Runs the offline capture pipeline:
  frame selection -> segmentation -> CLIP labels -> serial gemma naming ->
  inventory -> world fusion -> hub ingest
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --capture-dir)
      capture_dir="${2:-}"
      shift 2
      ;;
    --out-prefix)
      out_prefix="${2:-}"
      shift 2
      ;;
    --floor)
      floor="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$capture_dir" ]]; then
  echo "--capture-dir required" >&2
  usage >&2
  exit 2
fi
if [[ ! -d "$capture_dir" ]]; then
  echo "capture dir not found: $capture_dir" >&2
  exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "python not executable: $PYTHON" >&2
  exit 1
fi

video="$capture_dir/video.mov"
poses="$capture_dir/poses.ndjson"
if [[ ! -f "$video" ]]; then
  echo "video not found: $video" >&2
  exit 1
fi

prefix_dir="$(dirname "$out_prefix")"
prefix_base="$(basename "$out_prefix")"
mkdir -p "$prefix_dir"
log_path="$prefix_dir/run_${prefix_base}.log"
: > "$log_path"

frames_dir="${out_prefix}_frames"
crops_dir="${out_prefix}_crops"
labels_json="${out_prefix}_labels.json"
named_json="${out_prefix}_named.json"
inventory_json="${out_prefix}_inventory.json"
inventory_html="${out_prefix}_inventory.html"
world_json="${out_prefix}_world.json"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$log_path"
}

run_stage() {
  local stage="$1"
  shift
  log "START $stage"
  set +e
  "$@" 2>&1 | tee -a "$log_path"
  local status="${PIPESTATUS[0]}"
  set -e
  if [[ "$status" -ne 0 ]]; then
    log "FAIL $stage status=$status"
    exit "$status"
  fi
  log "END $stage"
}

count_trusted() {
  "$PYTHON" - "$world_json" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    world = json.load(f)
objects = world.get("objects") if isinstance(world, dict) else []
trusted = [
    obj for obj in objects
    if isinstance(obj, dict) and str(obj.get("trust") or "trusted").lower() != "rejected"
]
print(len(trusted))
PY
}

log "PIPELINE capture_dir=$capture_dir out_prefix=$out_prefix floor=$floor"

if [[ -s "$poses" ]]; then
  run_stage "select sharp pose frames" \
    "$PYTHON" scripts/walk_select_sharp_frames.py \
      --poses "$poses" \
      --video "$video" \
      --out-dir "$frames_dir" \
      --target-fps 3.0 \
      --still-percentile 40
  fuse_poses_arg="$poses"
else
  log "poses.ndjson absent or empty; falling back to Laplacian frame extractor"
  run_stage "extract sharp frames fallback" \
    "$PYTHON" scripts/walk_extract_frames.py \
      --video "$video" \
      --out "$frames_dir" \
      --fps 2.0 \
      --min-sharpness 40.0
  fuse_poses_arg="NONE"
fi

run_stage "segment frames" \
  "$PYTHON" scripts/walk_segment_frames.py \
    --frames-dir "$frames_dir" \
    --out "$crops_dir"

run_stage "label crops" \
  "$PYTHON" scripts/walk_label_crops.py \
    --crops "$crops_dir/crops_manifest.json" \
    --out "$labels_json"

run_stage "name objects with gemma serial" \
  "$PYTHON" scripts/walk_name_objects.py \
    --labels "$labels_json" \
    --crops-dir "$crops_dir" \
    --out "$named_json" \
    --score-floor "$floor" \
    --model gemma3:12b-it-qat \
    --progress-every 20

run_stage "build inventory" \
  "$PYTHON" scripts/walk_build_inventory.py \
    --labels "$named_json" \
    --out-html "$inventory_html" \
    --out-json "$inventory_json" \
    --score-floor "$floor"

run_stage "fuse world" \
  "$PYTHON" scripts/walk_fuse_world.py \
    --inventory "$inventory_json" \
    --labels "$named_json" \
    --frames-manifest "$frames_dir/manifest.json" \
    --poses "$fuse_poses_arg" \
    --out "$world_json"

run_stage "ingest walk world" \
  "$PYTHON" scripts/ingest_walk_world.py \
    --world "$world_json"

trusted_distinct="$(count_trusted)"
log "PIPELINE DONE ${trusted_distinct} trusted objects"
