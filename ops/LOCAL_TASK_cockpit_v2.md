# LOCAL TASK — cockpit v2 (qwen, single file, founder-facing)

Rewrite scripts/ops_cockpit.py (port 8788, stdlib only) FOR THE FOUNDER:
1. Top ALERT banner (red) when: hub :8765 not 200, dashboard :8777 not
   200, no cable-sync "replayed" line in last 5 min (parse last timestamp
   in /tmp/cable_sync_loop.log), or codex log's last line contains
   "error"/"limit". Green "ALL SYSTEMS GO" otherwise.
2. "YOUR ACTION" box: read /tmp/soma_founder_request.txt if non-empty and
   newer than /tmp/soma_founder_reply.txt, show it big; else "nothing
   needed from you".
3. WORKERS table: Codex (pgrep codex; STATE running/idle; last 5 log
   lines), Local LLM (:1234 models or "ollama on demand"), cable-sync
   (last replay time + packet count), gates (parse last line of
   /tmp/soma_gates.txt if present: "tests OK/FAIL north-star X").
4. Phone: parse /tmp/soma_latest_spatial_pull.txt path, show object count
   from its spatial_world.json if readable.
5. Progress bar per gate G1-G4: read ops/gates_status.json
   {"G1":"partial","G2":"pending",...} — render colored bar.
Keep dark theme, refresh 5s, html.escape everything, every section
crash-proof (try/except → 'n/a').
