# HANDOFF — for the next Chief chat (resume here)
*Rewritten 2026-06-25. Branch `chief/p0-honesty-sprint`, cwd `/Users/zer00/Documents/VLM`. Founder =
Satoshi (KIT; thesis at Max Planck IPP Garching). You are the Chief (autonomous). The founder is near
the Claude usage limit — preserve YOUR tokens, run LOCAL LLMs (ollama gemma3:12b/27b) majorly.*

## ⛔ READ THIS FIRST — the recurring, founder-infuriating mistake (do NOT repeat it)
**The product is NOT OCR. OCR is ONE channel of ~12, and the founder declared it "solved and closed"
(twice, verbatim: "Are we building a glorified OCR scanner? No… Abandon OCR completely").** Two Chief
instances (incl. me) tunnel-visioned back into OCR — building OCR-only eval harnesses and an OCR-only
web app — and got the same furious correction each time. **If you find yourself optimizing OCR, OCR
text recall, caption-density, or a browser/web capture page: STOP. You have tunnel-visioned. Re-read
`ops/PRODUCT_NORTH_STAR.md` + `ops/ANTI_TUNNEL_LEASH.md`.**

## THE PRODUCT (the real thing, from the finalised blueprint)
A **wearable continuous context engine**, `HELPERS → INJECTION → LLM`:
- **HELPERS (on the PHONE, multi-modal):** FastVLM (SCENE caption) + YOLO (OBJECTS/detector) + Apple
  Vision OCR + speech + GPS — fused into derived OBJECT/EVENT text. Proven live in Munich 2026-06-04.
- **The phone is the INPUT DEVICE.** It perceives, keeps ONLY derived text (no raw media ever), and
  POSTs to the Mac.
- **BRAIN (on the MAC):** `scripts/ask_home.py` fuses ~12 specialists (scene/objects/temporal/spatial/
  egomotion/audio/speech/entity-graph/counting/self-wearer/structured-recall/premise-gate/consensus) →
  answers honestly (reads-or-refuses) → **INJECTION/EXPAND** attaches world knowledge → two-zone answer
  (`personal_evidence` = what you saw, citable | `world_context` = world knowledge, fenced, never a
  personal claim). "Ask on the Mac" is the founder's chosen model — phone captures, Mac answers.
Privacy: no raw media stored/leaves; derived text free; PII scrubbed at the storage seam (wired+tested).
The moat is **honesty** (binds/reads-or-refuses, fenced world knowledge), never confident fabrication.

## ⚠️ REALITY CHECK (2026-06-25, later) — NOT demo-ready; core perception is UNRELIABLE
The loop is deployed and the pieces connect, but on REAL on-phone captures the perception is
garbage: the on-device VLM (FastVLM) echoes its prompt template, stuffs "yes", hallucinates
attributes (Pringles→"Metal spoon"), and reads on-screen text (incl. our own messages, a YouTube
video) as world facts; the flat-string memory has no quality floor, so the brain answers from the
garbage (e.g. "spoon: yes, metal" — invented). "Demo-ready" is RETRACTED. Active overhaul: make the
tiny VLM do loose perception only, build a Mac-side INJECT layer (structure/bind/quality-gate +
screen-content filter), restructure ask-time for speed, then measure honestly. See the cycle-14
plan in ops/SOVEREIGN_STATE.md.

## ███ DEPLOYED STATE (the loop connects, pieces in place) ███
1. **Native multi-modal app: BUILT + INSTALLED on the iPhone** (`de.zer00.trace`, iPhone 17, Xcode 26.3,
   team K84R7AX3YW, automatic signing). Source: `trace-native-fastvlm/` (scheme **"FastVLM App"**, NOT
   the shared "FastVLM" scheme which builds only the framework). **Xcode/deploy is NOT blocked** — the
   old `ios26-xcode-deploy-constraint` memory was STALE and caused the OCR-web-app detour.
   - Build: `xcodebuild -project FastVLM.xcodeproj -scheme "FastVLM App" -destination
     'platform=iOS,id=00008150-001460D83686401C' -allowProvisioningUpdates -configuration Debug
     -derivedDataPath build/dd build` (from `trace-native-fastvlm/`).
   - Install: `xcrun devicectl device install app --device D3A506B2-8923-5313-B8A3-FF769ABBA228
     "build/dd/Build/Products/Debug-iphoneos/FastVLM App.app"`.
   - The app POSTs to the Mac brain at `http://172.20.10.6:8765` (baked in `ContentView.swift:36`,
     overridable in-app via the brain icon → set `http://<mac-lan-ip>:8765` if the WiFi IP changes).
2. **Mac brain: LIVE** — `scripts/trace_brain_server.py` on `:8765` (`/health`, `/ingest`, `/ask`),
   LAN-reachable at `172.20.10.6:8765`. Runs `ask_home.ask_with_understanding` (the 12-channel brain +
   EXPAND). Launch: `TRACE_BIND=0.0.0.0 TRACE_BRAIN_PORT=8765 PYTHONUNBUFFERED=1 nohup caffeinate -is
   .venv/bin/python scripts/trace_brain_server.py > /tmp/trace_brain.log 2>&1 & disown`.
3. **The full loop VERIFIED end-to-end (Mac side, simulated capture):** ingest SCENE+OBJECTS+detector →
   ask "what kind of place is this?" → grounded two-zone answer ("You saw a night street with a Swatch
   store, McDonald's… / Swatch: a watch brand…"). The paradigm runs, on-device oracle, zero egress.
4. **Cockpit:** `scripts/cockpit_ask_server.py` on `:8799` (`/ops` glance board, `/engine`). Data in
   `ops/cockpit/*` (gitignored runtime state). Logger `scripts/clog.py` → flight recorder.
5. **RETIRED — do NOT revive:** `scripts/trace_app.py` (an OCR-only LAN web app + `web/trace_app.html`,
   `scripts/phone_perceive.py`) — the tunnel. The native app supersedes it entirely.

## WHAT TO DO NEXT (real frontiers — verify the capture, then the substrate, then the number)
1. **TEST THE REAL ON-PHONE CAPTURE** (the immediate next step; needs the founder to open the app).
   Open TRACE on the iPhone → grant camera + trust the developer profile (Settings → General → VPN &
   Device Management) → point at a scene → ask. Observe FastVLM/YOLO/OCR/speech quality + pace live.
   Munich report flagged OCR-accept weak, vision/detector strong. Tune capture from what's actually weak.
2. **Typed event-log substrate (blueprint CL-1).** Memory is still a flat string dossier; the blueprint's
   root move is a typed append-only `Observation` event log (`src/trace_memory/domain/observation.py`
   exists; `adapters/sqlite_eventlog.py` seed exists). Make it load-bearing. Enables binding + persistence.
3. **Premise-gate 3-mode (ANSWER/CORRECT/REFUSE)** at the `build_evidence_dossier` seam + populate
   `refutation_cue` (blueprint §4). The WS1 self/world guard (`scripts/self_world_guard.py`) is a
   structural piece of this already.
4. **The trustworthy number (the pitch gate):** n≥100 frozen human gold on REAL multi-modal captures
   (not OCR-only), score the real `ask_home`, 95% CIs, target ≥40% correct / <10% halluc. Needs founder.

## WHAT WAS BUILT THIS SPRINT — real vs dead-end (don't repeat the dead-ends)
- **REAL, keep:** EXPAND/understanding layer (`inject_expand.py`, commit de7d581 — the paradigm "Prompt");
  WS1 self/world binding guard (`self_world_guard.py`, 29d3030 — kills "a sign's name became my name");
  temporal/identity binder (`inject_bind.py`, 40eebb9, validated 96.9% precision, wired for recurrence);
  PII scrub at storage seams; the anti-tunnel leash.
- **DEAD-ENDS, measured, do NOT repeat:** the OCR web app (346d6d5 — retire it); caption-enrichment
  experiments on Mac OCR/caption-only memories — dense (43.2%/13.6%), merge (38.6%/15.0%), 27b
  (40.9%/14.3%) all WORSE than base (45.5%/4.8%). **Lesson: more text/capacity WITHOUT binding raises
  hallucination** (blueprint §5.1, measured 4 ways). Those Mac memories are a DEGENERATE single-channel
  slice; the real capture is the native multi-modal one.

## HONEST NUMBERS (what they mean)
- The 44-question battery on OCR/caption-only Mac memory caps ~45.5% correct / 4.8% halluc. That's the
  BLINDFOLDED proxy (no live multi-modal capture). It is NOT the product number. The real number needs
  the native multi-modal capture + n≥100 gold (above). Do NOT grind the 44 further — it's capped + it's
  the wrong (OCR/caption-only) substrate.

## OPERATING RULES
- Local LLMs majorly; Codex sparingly + time-boxed; preserve Claude tokens.
- Harness-tracked background jobs (`run_in_background`) for work you must track — they NOTIFY you on
  completion. Detached `nohup`+`caffeinate` ONLY for persistent services (brain/cockpit) — they go dark.
- No raw media stored/leaves; personal_evidence vs world_context never merge; LLM self-confidence is
  worthless (gate on geometry/corroboration — the ZLORPTECH lesson).
- Run the leash every cycle; every `[STATE_MANIFEST]` carries a `LEASH:` line. One demo ≠ verified.

## KEY FILES / SERVICES
- Brain: `scripts/ask_home.py` (`ask`, `ask_with_understanding`). EXPAND: `scripts/inject_expand.py`.
  Guard: `scripts/self_world_guard.py`. Binder: `scripts/inject_bind.py`. Self: `scripts/self_entity.py`.
- Phone↔Mac: `scripts/trace_brain_server.py` (:8765, /ingest + /ask). Native app: `trace-native-fastvlm/`.
- Cockpit: `scripts/cockpit_ask_server.py` (:8799/ops). Logger: `scripts/clog.py`.
- Architecture: `ops/PRODUCT_NORTH_STAR.md`, `ops/CONTEXT_ENGINE_BLUEPRINT_2026-06-23.md` (the spine),
  `ops/ANTI_TUNNEL_LEASH.md`, `ops/SOVEREIGN_STATE.md` (newest [STATE_MANIFEST] at bottom), this file.
- The full prior-session transcript (architecture finalisation) was at `/Users/zer00/Downloads/Claude
  Code.mhtml` → extracted to `/tmp/sess_clean.txt`; the founder considers it canonical context.
```
```
