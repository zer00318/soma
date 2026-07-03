# P22 — Motion/IMU activity channel
wave: W2 · tag: mechanical · executor: Sonnet or local LLM (Opus effort=low) · depends: P02

## Context (self-contained)
The phone knows walking/driving/stationary/cycling for free (CoreMotion
CMMotionActivityManager) and the memory ignores it. This is the cheapest coverage win and
the key episode-boundary signal for the future digest pyramid (P30): "when did I leave for
the lab" is a motion question. The iOS app lives in `trace-native-fastvlm/FastVLM App/`;
observations flow through the P02 contract to the hub.

## Laws that bind you
L1 (metadata only — trivially satisfied). L5. Do not touch answering logic.

## Do
1. Swift: subscribe to CMMotionActivityManager during capture; emit an observation on
   activity-state CHANGE only (`helper_id=motion_activity`, text like
   "motion: stationary → walking", confidence from CMMotionActivity.confidence), plus a
   low-rate heartbeat (~1/min) with current state.
2. Pair with the existing GPS/place channel: state changes carry the current place string
   when available.
3. Seam test through real Hub.ingest; iOS build must stay green (`scripts/deploy_ios.sh`
   builds; do not deploy — that's the founder's step).

## Done when
A real pocket walk produces a readable motion trail in the store (state changes with
timestamps); "was I walking or sitting at 14:30" answers or hedges honestly through /ask;
pytest + battery hold; iOS build green. INDEX flipped.
