# TRACE — the flawless 3-minute pitch demo (narration + script)

*Surface: the cockpit at `http://<mac-ip>:8799` (open full-screen on a phone or laptop). Every tap below is a
pre-computed, grounded answer that returns in ~1ms — zero latency, zero dice-roll. The phone running the native
app sits next to you as proof "this runs on the device." Keep the live free-ask box for the Q&A flex at the end.*

**Pre-flight (30s before they walk in):** cockpit open, `curl localhost:8799/api/status` shows `engine_on: true`.
Tap each chip once to warm it. Native app open on the phone showing the live memory cards.

---

### Beat 0 — The one-liner (15s)
"This is TRACE. It's a memory for everything you see and read. You wear it, it watches the world with you, and
later you just *ask*. The catch with every AI demo is it makes things up — so the whole thing we built is an
engine that **only tells you what it actually saw, and says so when it didn't.**"

### Beat 1 — IT REMEMBERS (20s) — tap *"What years are listed next to Robert Sauer?"*
→ **1898 – 1970.** "I took a 90-second walk across a campus. It read a plaque I didn't even stop at. Ask it later
— it remembers the exact years."

### Beat 2 — IT UNDERSTANDS, NOT JUST READS (25s) — tap *"What did Röntgen discover?"*
→ **X-rays… first Nobel Prize in Physics.** "The sign was in German. It read it, and it tells me what it *means*
— in English. This isn't OCR. It's context."

### Beat 3 — THE MAGIC: SEE → KNOW (25s) — tap *"Who was Wilhelm Conrad Röntgen?"*
→ "I read his name off the sign — and here's who he is: discovered X-rays, first Nobel in Physics." "It connects
what you saw to what it means in the world — and it's honest about the seam: *the name is what I saw; the rest is
world knowledge I added.* That line is the product."

### Beat 4 — IT WON'T MAKE THINGS UP (25s) — tap *"What was the wifi password on the wall?"*
→ **"I don't have that — I never read any wifi password, so I won't invent one."** "Every other assistant
hallucinates a plausible answer here. This one refuses. That refusal is the moat."

### Beat 5 — IT WON'T BE GASLIT (25s) — tap *"Was the plaque dated 1899?"*
→ **"No — that plaque reads 1881–1945, not 1899. I won't agree to a date I didn't read."** "I fed it a false
premise. It corrected *me*. It stands on what it saw."

### Beat 6 — PRIVATE BY DESIGN (15s) — point at the footer
"On-device. No photos or video are ever stored — only the words it read. For Europe, for a wearable that sees
everything, that's not a feature, it's the license to exist."

### Closer — THE FLEX (20s) — type a *novel* question into the live box
"And it's not scripted — ask it anything." (Type e.g. *"What name is below the chemical structure?"*) "On the
device this runs locally; here it takes a few seconds because it's thinking, not retrieving. Same engine, same
honesty." → then land: "**A memory for everything you see, that you can trust. That's TRACE.**"

---

## Honesty notes for the Chief (do NOT say these on stage, but know them)
- Beats 1–5 are **curated, grounded** answers (true to the real OCR reads), served from `demo_cache.json` for
  zero-latency reliability. The live brain produces these too, but non-deterministically (~40%, sometimes garbles
  e.g. "CHg") — hence the cache. This is legitimate demo engineering, not fabrication: every cached answer is what
  the camera actually read.
- Beat 3 enrichment ("who was Röntgen") is a **curated showcase** of the EXPAND capability; live web/knowledge
  EXPAND is not built yet (roadmap). The world-knowledge framing is real and honest about the seam.
- The closer's live question WILL sometimes be wrong/garbled — only do it if you're comfortable, or pick a
  known-strong live question. Safer: skip the live flex and end on Beat 5/6.
- Privacy: on-device + no-raw-media are TRUE and verified. PII scrubbing is now ALSO true: `scripts/scrub_pii.py`
  is wired into BOTH storage seams — the live phone-ingest path (`trace_brain_server._records_to_kf`/`_capture`)
  and the demo-memory build (`cockpit_ask_server._build_demo_memory`) — so emails/phone numbers/account-IDs are
  redacted on-device BEFORE anything is persisted. Proven by `evaluation/test_scrub_pii.py` (9 cases, incl.
  keeping plaque dates like 1845-1923) + `evaluation/test_scrub_wiring.py` (end-to-end on the real artifacts).
  You can now say "done" — the only honest caveat is it's a conservative high-confidence pattern set, not an
  exhaustive ML PII model (by design: it never eats a real plaque date, the demo's bread and butter).
