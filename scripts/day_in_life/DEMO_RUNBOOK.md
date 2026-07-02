# TRACE — PITCH DEMO RUNBOOK

The demo that **works reliably**, in the order to run it. Read this once before you walk in.

---

## THE ONE-LINE STORY
> "I recorded my surroundings on my phone. It kept **no video** — only text, and the frames are
> already deleted. Now watch me ask my own memory anything — and watch it refuse to make things up."

Two moats, say them out loud: **runs on-device / frames deleted** (privacy) and **it refuses what
it didn't see** (honesty). Investors have all been burned by a confident-wrong chatbot — the refusal
is the thing they remember.

---

## BEFORE THE ROOM (5 min, one time)
1. Mac + phone on the **same Wi-Fi**.
2. Start the backend on your **desk/room store** (the reliable one):
   ```
   .venv/bin/python scripts/trace_hub.py --store data/trace_store.sqlite3 --port 8765
   ```
   (or `scripts/day_in_life/demo.sh` to demo the day-in-life store instead — see caveat below.)
3. Warm the model so the first answer isn't slow — the launcher does this; if running the hub
   directly, ask one throwaway question first.
4. Phone: brain icon → `http://<mac-ip>:8765`. Confirm the "brain connected" light is green.
5. Laptop/projector view (optional, looks great): open `http://127.0.0.1:8765/` — the ask box shows
   the answer, a **firm/hedged/refused badge**, and the **evidence rows** it used.

**Latency to expect:** counting / "is there…" questions are **instant (<1s)**. Free-text recall is
**~10-12s** on the local model — the UI shows "thinking"; that's normal, not a hang. Don't fill the
silence apologetically — say *"it's reasoning over everything it saw, on this machine, no cloud."*

---

## THE 3-PART FLOW

### Part 1 — "It's remembering, live" (30s)
Open the app, slowly pan the phone across the desk/room. The memory feed fills with text records
(objects, text it reads, speech). Point at the screen: *"Every line is what it just perceived — and
the picture is already gone. This is all that's kept."*

### Part 2 — "Here's a full day" (the video)
Play your day-in-life screen recording. This is the **vision** — narrate it as where this goes:
a whole day, remembered, searchable. (Do **not** live-query the montage — see caveat.)

### Part 3 — "Ask it anything" (the payload — use THESE questions, in this order)
Ask in the app (or type on the projector page). Vetted on the real desk store — they land:

**Open with instant + wow:**
1. **"How many mice are on the desk?"** → *"1"* (firm) — instant.
2. **"How many keyboards do I have?"** → *"between 2 and 3"* — instant. **Say the line:**
   *"Notice it didn't guess a number — it tells me the range it can actually defend. That's honesty."*
3. **"What is on my desk?"** → lists the real objects (~10s).

**Then the honesty turn (the moment they remember):**
4. **"Is there a bicycle on my desk?"** → *"No — I have no record of a bicycle."* — instant.
5. **"You saw my red Ferrari earlier — where is it?"** → it does **not** confirm the Ferrari; it
   corrects to what was actually there. **Say:** *"Every other assistant would have invented a
   location. Ours would rather be honest."*
6. **"How many unicorns are on the desk?"** → refuses / "no unicorns." (crowd-pleaser)

**Close on evidence:**
7. **"Where is my laptop?"** → answer **with the evidence rows visible** on the projector page.
   *"It doesn't just answer — it shows you the receipts."*

> Keep it to ~6-7 questions. Lead with the instant ones so there's no dead air. If you improvised a
> live capture in Part 1, you can ask about **that** room instead — same question shapes work.

---

## DAY-IN-LIFE MONTAGE — honest caveat (read before choosing to show it)
The `Day in the life.mp4` clip is the **hard case**: fast cuts + tiny on-screen text + rushed audio.
On the current single-pass local capture it reliably answers only ~4-5 of the 19 blind questions
(bedsheets colour, glasses, watch, the breakfast scene, the person at the counter) — **with zero
made-up answers**. It is a great "here's the vision" *video*, but do **not** live-query it in front of
investors expecting 19/19. If asked "can it do a whole day?", say honestly: *"That's what we're scaling
to — capture fidelity on small text is the current engineering frontier; the honesty and the recall
you just saw are already real."*

Reproduce the day-in-life numbers yourself:
```
.venv/bin/python scripts/day_in_life/perceive.py           # build the store (~15 min, one time)
.venv/bin/python scripts/day_in_life/score.py --model gemma3:12b-it-qat   # score the 19 Qs
```

## THE PROOF SLIDE (backup, if they push on rigor)
The reproducible instrument, one command, exit-1 on any confident-wrong answer:
```
.venv/bin/python evaluation/run_canonical_battery.py
```
**Last result (n=42, local gemma):** correct-on-present **96.7%** · refuse-on-absent **100%** ·
**confident-wrong 0** · paraphrase-parity **100%**. That's the honesty moat, measured.

---

## IF SOMETHING BREAKS
- **Answers slow / first one hangs:** the model was cold. Ask one throwaway question to warm it; keep
  it warm (the launcher pins it 30 min).
- **"Brain not connected" on the phone:** Mac IP changed or different Wi-Fi. Re-enter `http://<ip>:8765`.
  Check `curl http://127.0.0.1:8765/health` on the Mac → `{"ok": true}`.
- **Metal / out-of-memory error:** two models loaded at once. Run `scripts/day_in_life/demo.sh` (it
  evicts the spare model), or restart the hub — only the 12b model should be resident.
- **A question refuses when you expected an answer:** that's the moat being conservative, not a crash —
  rephrase with the object name, or move to the next scripted question. Never argue with it live.
