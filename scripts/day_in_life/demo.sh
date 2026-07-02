#!/bin/sh
# ONE-COMMAND DEMO LAUNCHER for the pitch.
#
#   scripts/day_in_life/demo.sh
#
# What it does:
#   1. Copies the committed day-in-life store to a SCRATCH demo store, so any live capture you
#      do during the demo (part 1, "show it remembering") never corrupts the committed one.
#   2. Runs the sleep binder on the scratch store (counts, landmarks, current-location).
#   3. Pins gemma warm and serves the hub at http://<this-mac-ip>:8765 on the scratch store.
#
# On the phone: brain icon -> http://<this-mac-ip>:8765 . Open the app to SEE memories + ask.
# The demo page (for a laptop/projector) is http://127.0.0.1:8765/ .
set -eu
cd "$(dirname "$0")/../.."

SRC="evaluation/day_in_life/day_in_life.sqlite3"
DEMO="evaluation/day_in_life/demo_live.sqlite3"
MODEL="${TRACE_DEMO_MODEL:-gemma3:12b-it-qat}"   # 12b = snappy; export TRACE_DEMO_MODEL=gemma3:27b-it-qat for max quality

if [ ! -f "$SRC" ]; then
  echo "! Committed store missing. Build it first (~15 min, one time):"
  echo "    .venv/bin/python scripts/day_in_life/perceive.py"
  exit 1
fi

echo "→ copying committed store to scratch demo store (live capture won't corrupt the original)"
cp "$SRC" "$DEMO"

echo "→ binding (counts / landmarks / current-location)"
.venv/bin/python - "$DEMO" <<'PY'
import sys
sys.path.insert(0, "src")
from trace_memory.store import TraceMemoryStore
from trace_memory.store.sleep import SleepConsolidator
from trace_memory.store.author import deterministic_author
store = TraceMemoryStore(sys.argv[1])
s = SleepConsolidator(store, author=deterministic_author).consolidate()
print(f"   authored {s.composed_memory_count} memories, {store.node_count()} nodes total")
PY

echo "→ freeing GPU: evicting other gemma models (prevents the 27b+12b out-of-memory on M2)"
for m in gemma3:27b-it-qat gemma3:12b-it-qat; do
  [ "$m" = "$MODEL" ] && continue
  curl -s http://127.0.0.1:11434/api/generate -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null 2>&1 || true
done
echo "→ pinning $MODEL warm in VRAM (first answer won't pay a cold load)"
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"ready\",\"stream\":false,\"keep_alive\":\"30m\"}" >/dev/null || true

IP=$(ipconfig getifaddr en0 2>/dev/null || echo "<this-mac-ip>")
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  DEMO READY"
echo "  Phone app brain icon → http://$IP:8765"
echo "  Projector / laptop    → http://127.0.0.1:8765/   (ask box + evidence)"
echo "  Answerer: $MODEL   Store: $DEMO"
echo "  Vetted questions that land: scripts/day_in_life/DEMO_RUNBOOK.md"
echo "════════════════════════════════════════════════════════════════"
echo ""
exec .venv/bin/python scripts/trace_hub.py --store "$DEMO" --port 8765
