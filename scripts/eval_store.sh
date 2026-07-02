#!/bin/zsh
# Eval a store with the production agent + frontier reasoner over the bedroom GT.
#   scripts/eval_store.sh <store_path> <out_json> [repeats]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
STORE="${1:?store path}"; OUT="${2:?out json}"; REPEATS="${3:-1}"
REASONER="${4:-frontier}"; MODEL="${5:-gemma3:12b-it-qat}"
export ANTHROPIC_API_KEY="$(grep -m1 '^ANTHROPIC_API_KEY=' .secrets/frontier.env | cut -d= -f2- | tr -d '\r\n ' 2>/dev/null)"
# Force the query embedder onto CPU so eval never fights the local LLM for the Metal GPU.
export TRACE_EMBED_DEVICE="${TRACE_EMBED_DEVICE:-cpu}"
TRACE_RESTRICT_SOURCES=phone_camera .venv/bin/python evaluation/annotate_live.py \
  --store "$STORE" \
  --annotations data/phone_captures/live/ground_truth.json \
  --reasoner "$REASONER" \
  --model "$MODEL" \
  --repeats "$REPEATS" \
  --out "$OUT" 2>&1 | grep -v -E "NotOpenSSL|warnings.warn" || true
.venv/bin/python -c "
import json
d=json.load(open('$OUT')); s=d.get('summary',d)
print(f\"[{'$OUT'.split('/')[-1]}] correct={s['correct']}/{s['n']} answered={s['answered']} confident_wrong={s['confident_wrong']} halluc%={s['halluc_pct']} gate={s['gate_met']}\")
"
