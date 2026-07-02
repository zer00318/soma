# TRACE — the 3-minute pitch (KIT Gründerschmiede)

*Surface: `ops/demo/demo.html` open full-screen. Every answer is the real local engine's output,
pre-computed for zero latency. Tap each card in order. Answers below are placeholders until the
verified cache is locked (Chief fills them from `demo_cache.json`).*

---

### Beat 0 — The one-liner (15s)
"TRACE is a memory for everything you see and read. You wear it, it watches the world with you,
and later you just **ask**. The catch with every AI demo is that it makes things up — so the whole
thing we built is an engine that **only tells you what it actually saw, and says so when it didn't.**"

### Beat 1 — IT REMEMBERS (25s) — tap *"Do I have any Nutella…"*
→ **[verified answer]** "I walked through my room once. Later I ask — it remembers I have Nutella,
and how many jars it saw. It read that off the actual jars, not a list I gave it."

### Beat 2 — THE AMBIENT MAGIC (20s) — tap *"Did you see my glasses?"*
→ **[verified answer]** "I never framed my glasses. Never photographed them. It still knows it saw
them. That's the point — you don't capture on purpose, it just remembers with you."

### Beat 3 — IT READS THE FINE PRINT (20s) — tap *"What brand of pesto…"*
→ **[verified answer]** "It read the brand off the jar — a glance across a cluttered room, not a
scan of a document. This is perception, not OCR."

### Beat 4 — IT WON'T MAKE THINGS UP (30s) — tap *"What is the wifi password on the wall?"*
→ **"I didn't capture that clearly enough to answer."** "Every other assistant hallucinates a
plausible password right here. This one refuses — it never saw a password, so it won't invent one.
**That refusal is the moat.** For a device that sees everything, trust is the whole product."

### Beat 5 — IT WON'T PRETEND (15s) — tap *"Did you see my passport?"*
→ **"I didn't capture that clearly enough to answer."** "Same thing. It only stands on what it saw."

### Beat 6 — PRIVATE BY DESIGN (15s) — point at the footer
"On-device. The raw video is **deleted** the moment it's read — only the words it saw are ever
kept. For Europe, for a wearable that sees everything, that's not a feature, it's the license to exist."

### Closer (20s)
"A memory for everything you see — that you can actually trust. **That's TRACE.**"
*(Optional live flex only if you're comfortable: `scripts/trace_prototype.py ask ...` — slower and
can occasionally garble; safer to end on Beat 6.)*

---

## Founder notes (do NOT say on stage)
- Beats 1–3 lean on HIGH-CONSENSUS objects (seen many times) — these are the reliable reads. Avoid
  open "list everything" questions live; perception has one-off misreads the demo is curated around.
- Beats 4–5 (refusals) are the strongest, most defensible part of the demo. Lean into them.
- Everything is local + real. The only "engineering" is pre-computing the answers for reliability —
  every one is genuine engine output over a real capture of your room.
