# S8 / TASK 08 — BEDROOM CAPTURE OVERHAUL
*SERIAL. This task prepares and validates the capture lane that gives the biggest lift.*

## GOAL
The current bedroom frontier run proved the biggest lever is **better capture on the exact
founder questions**, not more side features. Build the machine-side probe so we know whether a
new capture actually contains the facts before wasting time patching the brain.

## INPUT CONTEXT
- `scripts/probe_bedroom_coverage.py`
- `scripts/run_frontier_room_cycle.sh`
- `scripts/select_keyframes.py`
- `scripts/light_ingest.py`
- `evaluation/annotate_live.py`
- `data/phone_captures/bedroom_dense_353f`
- `data/phone_captures/live/ground_truth.json`

## EXACT DIRECTIVE
1. Run the frontier room cycle on the latest dense bedroom capture.
2. Read the coverage probe output before reading the answer score.
3. Produce a capture-gap list of the missing signals only:
   `battery`, `app`, `diary`, `pillows`, `jar count`, `microphone`, etc.
4. Convert that list into a founder recapture dwell checklist with exact objects to pause on.
5. Do NOT patch the brain yet unless the coverage probe says the missing evidence is already in the store.

## VALIDATION METRIC
- `scripts/run_frontier_room_cycle.sh` exits 0.
- `scripts/probe_bedroom_coverage.py` prints a machine-readable summary of present vs missing signals.
- The resulting gap list names only evidence that is absent or weak in the store, not speculative causes.
