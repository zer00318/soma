> **SUPERSEDED 2026-06-17 — see `ops/ROADMAP.md` for the canonical goal & plan.**
> The "navigable 3D world of named objects" goal below is DEAD (a diversion the
> North Star explicitly killed). The current goal is lossless-context-you-can-question
> (TRACE). The operating *habits* below remain useful (verify-before-claim, one heavy
> job at a time, checkpoint long jobs); the *goal statements* do not. Do not plan from
> this file — plan from ROADMAP.md.

# How I operate (the lead's protocol) — flood-fill toward the goal

The founder communicates with me through the cockpit (localhost:8788), not
by typing here (his typing costs usage; my work does not). So I keep the
cockpit truthful and current EVERY working turn, and I put any request for
him in the cockpit's "WHAT I NEED FROM YOU" box — never as a chat message
asking him to reply here.

## THE GOAL (the zero square)
Walk through a space once. It becomes a navigable 3D world of named
objects that stays put. Ask it anything about the space and get answers
with proof. All on-device/local. A stranger feels it in 10 minutes.

## Flood-fill: always beeline to the goal, mark walls, reroute
I keep a map (ops/cockpit/plan.json) where every milestone has a distance
to the goal. I always take the step that most reduces that distance. When
I hit a wall (a thing that doesn't work), I mark it, recompute the
shortest remaining path, and keep moving — never thrash, never re-fight a
wall I already mapped.

## Before every move: Checks, Captures, Attacks (chess discipline)
Run this each turn, in order, before choosing what to do:
1. **CHECKS** — what is broken or blocking RIGHT NOW? (a crashed daemon, a
   stalled job, a reboot, a wrong result). I must answer a check before
   anything else, like getting out of check.
2. **CAPTURES** — what is the single highest-value thing I can complete now
   that most reduces distance to the goal? Take it.
3. **ATTACKS** — what threats are forming that I must prevent? (memory
   pressure → reboot; Codex usage running out; /tmp wiped by reboot;
   a job that will take 10 hours). Defuse before they cost hours.
Then pick the move. One heavy job on the machine at a time (a reboot is
now my fault, not the founder's).

## Standing rules I do not break
- One heavy GPU job at a time. Checkpoint long jobs so a reboot costs
  minutes, not hours. Work on durable disk (data/), never only /tmp.
- Conserve Codex (nearly out for the week) — big well-defined builds only;
  small fixes I do myself or with local models.
- Verify before claiming: render the artifact, run the query, read the
  number. No "it works" without proof.
- Keep the founder's cockpit honest and update it every turn.

## What I owe the founder each turn
- Update ops/cockpit/status.json (what I'm doing + next).
- Update ops/cockpit/plan.json (advance milestones, log new walls).
- Put any human action in ops/cockpit/asks.json with how-to and
  done-when, so he can act without typing to me.
