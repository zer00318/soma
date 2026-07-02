#!/bin/zsh
# Wait for the in-flight LLM rebind to finish, then eval the full LLM store and a
# composed-value-filtered variant. Emits both numbers for comparison vs baseline (8/21).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
REBIND_OUT="$1"

echo "[await] waiting for LLM rebind to finish..."
until grep -q "rebind\] [0-9]" "$REBIND_OUT" 2>/dev/null; do sleep 20; done
echo "[await] rebind done:"; grep "rebind\]" "$REBIND_OUT" | tail -2

# 1) Full LLM store as-is.
TRACE_EMBED_DEVICE=cpu scripts/eval_store.sh data/trace_store_rebind.sqlite3 evaluation/ras/treatment_llm.json 1

# 2) Composed-value-filtered variant: drop authored entity memories that compose nothing
#    (no count, no current_location, no contradictions, <3 supports). Groups always kept.
cp data/trace_store_rebind.sqlite3 data/trace_store_rebind_llm_filt.sqlite3
.venv/bin/python - <<'PY'
import sqlite3, json
con = sqlite3.connect('data/trace_store_rebind_llm_filt.sqlite3'); con.row_factory=sqlite3.Row
cur = con.cursor()
drop = []
for r in cur.execute("SELECT id, node_type, source_support_json, metadata_json FROM memory_nodes WHERE node_type IN ('entity_memory','group_memory')"):
    if r['node_type'] == 'group_memory':
        continue
    md = json.loads(r['metadata_json'] or '{}')
    sup = json.loads(r['source_support_json'] or '{}').get('support_ids') or md.get('support_ids') or []
    composes = (md.get('count') is not None) or bool(md.get('current_location')) or bool(md.get('contradictions')) or (len(sup) >= 3)
    if not composes:
        drop.append(r['id'])
q = ",".join("?" for _ in drop) or "''"
if drop:
    cur.execute(f"DELETE FROM memory_links WHERE to_id IN ({q}) OR from_id IN ({q})", drop + drop)
    cur.execute(f"DELETE FROM memory_nodes WHERE id IN ({q})", drop)
    con.commit()
print(f"[filter] dropped {len(drop)} non-composing authored memories")
con.close()
PY
TRACE_EMBED_DEVICE=cpu scripts/eval_store.sh data/trace_store_rebind_llm_filt.sqlite3 evaluation/ras/treatment_llm_filt.json 1

echo "[await] DONE. baseline=8/21"
