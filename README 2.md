# SOMA

SOMA is a local-first context engine.

What stays in this repo now:

- `soma_hub/` — local hub, graph, importer, recall, API
- `soma_perception/` — local perception workers
- `soma-native-fastvlm/` — native macOS/iOS capture app
- `scripts/` — only the scripts still useful for running, auditing, and supervising
- `tests/` — current test coverage

What was removed:

- old web/mobile experiments
- abandoned planner/backlog machinery
- stale reports, screenshots, and duplicate docs
- dead helper scripts that were only for deleted paths

## Core rules

- raw audio/video should stay ephemeral
- stored memory should be text/graph only
- recall should flow through the graph, not raw dumps
- keep the repo small and operational

## Run the hub

```bash
python3 -m soma_hub serve --host 127.0.0.1 --port 8765 --data-dir data --token dev-token
```

## Quick CLI checks

```bash
python3 -m soma_hub ingest "I put my keys in the black backpack near the entry table."
python3 -m soma_hub chat "Where are my keys?"
python3 -m unittest discover -s tests
```

## Live graph audit

```bash
./scripts/live_graph_audit.sh
```

Or once:

```bash
python3 scripts/audit_live_graph.py --base-url http://127.0.0.1:8765 --token dev-token
```

## Local model worker

Start the local LM Studio worker stack:

```bash
./scripts/start_local_worker_stack.sh
```

Send a bounded task:

```bash
python3 scripts/local_model_worker.py --model soma-local-worker --mode scout --task "Summarize likely risks in this file." --context-file /Users/zer00/Documents/VLM/soma_hub/graph.py
```

## Claude supervisor loop

This is the practical “run forever” entrypoint from the CLI:

```bash
cd /Users/zer00/Documents/VLM
nohup ./scripts/run_claude_supervisor_forever.sh > .soma_supervisor/runner.log 2>&1 &
```

Watch it:

```bash
tail -f /Users/zer00/Documents/VLM/.soma_supervisor/runner.log
```

How it works:

- uses one persistent Claude session
- lets Claude delegate to local workers
- sleeps while cheaper workers are busy
- sleeps through Claude usage-limit windows, then resumes

If Claude needs a real-world test from you, check:

- `/Users/zer00/Documents/VLM/.soma_supervisor/USER_TEST_REQUEST.txt`

Reply by writing anything into:

- `/Users/zer00/Documents/VLM/.soma_supervisor/USER_TEST_ACK.txt`
