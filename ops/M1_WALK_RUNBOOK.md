# M1 — First worn-POV walk (founder runbook)

Goal: the first real Retroactive Answerability Score. ~2–3h chest-mounted
walk (Garching), then a blind question battery the same evening.

## Before leaving (2 min)

1. Phone on the chest mount, FastVLM app open, camera view live.
   (Auto-lock is handled — the app disables the idle timer while running.)
2. Don't worry about WiFi: away from home the app cannot reach the hub and
   will spool every packet to a file on the phone instead. Nothing is lost.
3. Battery note: note the % when you leave. The drain number is M1 data.

## During the walk

- Walk normally. Do NOT perform for the camera — the point is what it
  catches without being told. Pause/cover the lens anywhere recording feels
  wrong (toilets, other people's screens, anyone who asks).
- One deliberate moment: stand ~2s in front of at least one text surface
  (flyer, poster, sign). The robotics-week-flyer question class is an M2
  acceptance test; M1 just needs the raw material.

## After the walk (10 min, phone unlocked + cable)

```bash
cd /Users/zer00/Documents/VLM

# 1. Pull the spool off the phone (note the TRACE/ subdirectory)
xcrun devicectl device copy from \
  --device D3A506B2-8923-5313-B8A3-FF769ABBA228 \
  --domain-type appDataContainer --domain-identifier de.zer00.trace \
  --source "Library/Application Support/TRACE/perception_spool.ndjson" \
  --destination /tmp/perception_spool.ndjson

# 2. Stop daemons, replay with original walk timestamps, restart
pkill -f trace_hub.api; pkill -f trace_perception.enricher
python3 scripts/replay_perception_spool.py /tmp/perception_spool.ndjson
nohup python3 -m trace_hub.api --host 0.0.0.0 --port 8765 >> /tmp/trace_hub_err.log 2>&1 &
nohup python3 -m trace_perception.enricher --db data/trace_hub.sqlite3 >> /tmp/trace_enricher.log 2>&1 &

# 3. Truncate the device spool so it is never replayed twice
: > /tmp/empty_spool.ndjson
xcrun devicectl device copy to \
  --device D3A506B2-8923-5313-B8A3-FF769ABBA228 \
  --domain-type appDataContainer --domain-identifier de.zer00.trace \
  --source /tmp/empty_spool.ndjson \
  --destination "Library/Application Support/TRACE/perception_spool.ndjson"
```

WiFi gotcha (learned in the 60s test): the Control Center WiFi toggle
DISCONNECTS but does not rejoin — after the walk, re-enable via
Settings → WLAN, or desk capture silently keeps spooling instead of
posting live. (Harmless — the spool catches everything — but replay
becomes a recurring chore instead of an offline-only path.)

## The same evening — the blind battery (this is the experiment)

1. WITHOUT looking at any logs, dashboards, or the replay output, write
   ~25 questions about your day into `evaluation/ras/walk1.txt`, one per
   line, prefixed with a category (objects/people/places/text/events/fusion):

   ```
   text: what did the poster near the Mensa say
   places: where was I around 15:00
   objects: what color was the bike I walked past
   ```

   Blindness is what makes the number honest — write what you actually
   wonder, not what you think it captured.

2. Run the battery and score it:

   ```bash
   python3 evaluation/run_ras.py ask --questions evaluation/ras/walk1.txt
   # fill each "verdict" in walk1.answers.json: correct | wrong | miss
   python3 evaluation/run_ras.py score --answers evaluation/ras/walk1.answers.json
   ```

3. Report back: RAS, hallucination rate, battery % consumed, and any
   moment the rig felt socially uncomfortable (that's M-late data too).

Expectations: the first number will be low — that's the point. It's the
baseline the pitch curve climbs from. Hallucinations matter more than
misses: a miss is a roadmap item, a hallucination is a product killer.
