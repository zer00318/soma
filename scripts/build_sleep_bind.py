#!/usr/bin/env python3
"""build_sleep_bind.py — SOMA sleep-pass binder.

Reads ALL channel logs from a walk memory directory, builds a condensed
evidence dossier, calls gemma3:12b-it-qat (via local ollama) to cross-link
entities and produce bound_memory.json.

Drafted by qwen2.5-coder:14b; integrated and hardened by Claude Code.

Usage:
    python build_sleep_bind.py <memory_dir>
    python build_sleep_bind.py --self-test
"""

import os
import json
import sys
import urllib.request
import urllib.error
import re

from artifact_provenance import source_fingerprint

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
GEMMA_MODEL = "gemma3:12b-it-qat"
OLLAMA_TIMEOUT = 600  # richer full-video + persistent-entity dossiers run locally
MAX_EVIDENCE_CHARS = 30000  # cover a full short clip, not only its first scenes

# ---------------------------------------------------------------------------
# Channel loaders
# ---------------------------------------------------------------------------

def _load_json(path):
    """Load JSON from path; return None (with warning) if missing or broken."""
    if not os.path.exists(path):
        print(f"  [skip] {os.path.basename(path)} not found")
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        print(f"  [warn] could not parse {os.path.basename(path)}: {exc}")
        return None


def load_channels(memory_dir):
    """Load all seven channel logs from memory_dir."""
    names = [
        "kf_memory.json",
        "micro_details.json",
        "screen_memory.json",
        "audio_events.json",
        "transcript.json",
        "asr.json",
        "world_memory.json",
        "attributes.json",
        "entity_centric.json",
    ]
    return {n: _load_json(os.path.join(memory_dir, n)) for n in names}


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------

def _extract_timestamped(channels):
    """Pull (t, source, text) triples from every channel that carries t."""
    rows = []

    kf = channels.get("kf_memory.json") or []
    if isinstance(kf, list):
        for item in kf:
            t = item.get("t", 0)
            parts = []
            cap = (item.get("caption") or "").strip()
            if cap:
                parts.append(f"CAPTION: {cap[:200]}")
            ocr = item.get("ocr") or []
            if ocr:
                parts.append(f"OCR: {' | '.join(ocr)}")
            if parts:
                rows.append((t, "kf", " ".join(parts)))

    micro = channels.get("micro_details.json") or []
    if isinstance(micro, list):
        for item in micro:
            t = item.get("t", 0)
            txt = " | ".join(item.get("micro_ocr") or []).strip()
            if txt:
                rows.append((t, "micro", f"REGION OCR: {txt}"))

    screen = channels.get("screen_memory.json") or []
    if isinstance(screen, list):
        for item in screen:
            t = item.get("t", 0)
            txt = (item.get("screen_ocr_txt") or " | ".join(item.get("screen_ocr") or [])).strip()
            if txt:
                rows.append((t, "screen", f"SCREEN OCR: {txt}"))

    rows.sort(key=lambda r: r[0])
    return rows


def _world_text(channels):
    """Flat text from world_memory objects."""
    wm = channels.get("world_memory.json")
    if not wm:
        return ""
    if isinstance(wm, list):
        objects = wm
    elif isinstance(wm, dict):
        objects = wm.get("objects") or []
    else:
        return ""
    lines = []
    for obj in objects:
        name = obj.get("name", "")
        attrs = obj.get("attributes") or ""
        where = obj.get("where") or ""
        lines.append(f"OBJECT: {name} — {attrs} — at: {where}")
    return "\n".join(lines)


def _transcript_text(channels):
    """Single line for transcript channel."""
    tr = channels.get("transcript.json")
    if not tr:
        asr = channels.get("asr.json") or {}
        segments = asr.get("segments") or []
        if segments:
            lines = ["[%.1f-%.1fs] %s" % (s.get("start", 0), s.get("end", 0),
                                            (s.get("text") or "").strip())
                     for s in segments if (s.get("text") or "").strip()]
            return "SPEECH: " + " | ".join(lines)
        return "(transcript: not available)"
    if not tr.get("usable_speech"):
        verdict = tr.get("verdict") or "no clear speech"
        return f"(transcript: {verdict})"
    text = (tr.get("text") or tr.get("raw_whisper") or "").strip()
    return f"SPEECH: {text[:500]}" if text else "(transcript: present but empty)"


def _audio_text(channels):
    """Single line for audio events channel."""
    ae = channels.get("audio_events.json")
    if not ae:
        return "(audio: not available)"
    db = ae.get("overall_db")
    if not ae.get("usable_sound"):
        return f"(audio: near-silent {db:.1f} dB, no distinct events)"
    events = ae.get("events") or []
    lines = [f"AUDIO overall {db:.1f} dB"]
    for ev in events[:5]:
        lines.append(f"  EVENT {ev.get('label')} {ev.get('start'):.1f}s-{ev.get('end'):.1f}s")
    return "\n".join(lines)


def _entity_text(channels, cap=60):
    """Persistent capture-bound entities, kept structured for the sleep pass."""
    entities = channels.get("entity_centric.json") or []
    if not isinstance(entities, list):
        return "(persistent entities: not available)"
    lines = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        attrs = []
        for attr in entity.get("attributes") or []:
            if not isinstance(attr, dict) or not attr.get("value"):
                continue
            attrs.append("%s=%s @%s" % (
                attr.get("attr", "attribute"), attr.get("value"), attr.get("frames") or []))
        if attrs:
            line = "%s %s | %s" % (
                str(entity.get("type") or "entity").upper(),
                entity.get("label") or entity.get("entity_id") or "unknown",
                "; ".join(attrs[:6]))
            lines.append(line[:360])
    if len(lines) > cap:
        last = len(lines) - 1
        lines = [lines[round(i * last / (cap - 1))] for i in range(cap)]
    return "\n".join(lines) if lines else "(persistent entities: empty)"


def build_evidence_dossier(channels, max_chars=MAX_EVIDENCE_CHARS):
    """Assemble condensed text evidence for gemma prompt."""
    rows = _extract_timestamped(channels)

    # Build timestamped block — group by 2-second buckets to reduce length
    bucket_text = {}
    for t, _src, text in rows:
        bucket = round(t / 2) * 2  # 2s buckets
        if bucket not in bucket_text:
            bucket_text[bucket] = []
        bucket_text[bucket].append(text)

    ts_block_parts = []
    total = 0
    for bucket in sorted(bucket_text):
        chunk = f"[t≈{bucket}s] " + " || ".join(bucket_text[bucket])
        total += len(chunk)
        if total > max_chars:
            ts_block_parts.append("... (truncated)")
            break
        ts_block_parts.append(chunk)

    ts_block = "\n".join(ts_block_parts)

    world_block = _world_text(channels)
    tr_block = _transcript_text(channels)
    audio_block = _audio_text(channels)
    entity_block = _entity_text(channels)

    dossier = f"""=== WORLD OBJECTS ===
{world_block}

=== SPEECH & AUDIO ===
{tr_block}
{audio_block}

=== PERSISTENT CAPTURE-BOUND ENTITIES ===
{entity_block}

=== TIMESTAMPED VISUAL EVIDENCE (OCR + captions) ===
{ts_block}
"""
    return dossier


# ---------------------------------------------------------------------------
# Gemma prompt builder
# ---------------------------------------------------------------------------

GEMMA_PROMPT_TEMPLATE = """You are a clip-agnostic MEMORY BINDER. Cross-link only facts that the
capture evidence below explicitly ties together. You have no ground truth and no knowledge of
which clip this is. Never import a fact from another recording or complete a corrupted name from
world knowledge.

EVIDENCE DOSSIER:
{dossier}

TASK: Produce ONLY valid JSON (no explanation, no markdown, just the JSON object) with this exact schema:
{{
  "entities": [
    {{"name": "...", "kind": "person|screen|sign|poster|place|object|event", "evidence": ["timestamp+verbatim snippet...", ...], "t_range": [first_t, last_t]}}
  ],
  "bindings": ["entity A is explicitly tied to detail B — evidence at t=..."],
  "poster_count": {{
    "n": 0,
    "names": [],
    "note": "Use only when posters are present; otherwise keep n=0 and names=[]"
  }},
  "summary": "2-4 sentence evidence-only recap"
}}

Rules:
- Every proper name, number, colour, logo, and place in the output must occur in the dossier.
- Bind attributes to a person/object only when one evidence line explicitly attaches them.
- Similar timing or proximity is not identity. Do not transfer a logo, outfit, or name between items.
- OCR is stronger than a scene-caption guess. Keep conflicting reads unresolved rather than choosing.
- Count distinct posters only when evidence distinguishes them. Do not count repeated frames.
- Empty entities/bindings are valid when evidence cannot support a safe cross-link.
- Output ONLY the JSON object. No markdown. No explanation.
"""


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def call_gemma(prompt_text):
    """POST to local ollama, return the response string or None on error."""
    payload = json.dumps({
        "model": GEMMA_MODEL,
        "prompt": prompt_text,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 2000, "num_ctx": 16384},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            return data.get("response", "")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"  [error] ollama request failed: {exc}")
        return None
    except Exception as exc:
        print(f"  [error] unexpected error calling ollama: {exc}")
        return None


# ---------------------------------------------------------------------------
# JSON extraction from gemma output
# ---------------------------------------------------------------------------

def extract_json(text):
    """Extract first valid JSON object from text (handles markdown fences)."""
    if not text:
        return None
    # Try direct parse first
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Try to extract from markdown fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find first { ... } block
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(stripped[start:end+1])
        except json.JSONDecodeError:
            pass
    return None


# ---------------------------------------------------------------------------
# Second-pass simpler prompt (fallback if first parse fails)
# ---------------------------------------------------------------------------

SIMPLE_PROMPT_TEMPLATE = """Return ONLY valid JSON using this schema:
{{"entities":[],"bindings":[],"poster_count":{{"n":0,"names":[],"note":""}},"summary":""}}
Populate it only from the evidence below. Every name and number must appear verbatim in the
evidence. Never infer identity from proximity and never use outside facts.

EVIDENCE:
{dossier}
"""


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_bind(memory_dir):
    """Main binding pipeline. Returns the bound_memory dict."""
    print(f"[sleep-bind] Reading channels from: {memory_dir}")
    channels = load_channels(memory_dir)

    print("[sleep-bind] Building evidence dossier...")
    dossier = build_evidence_dossier(channels)
    print(f"  Dossier length: {len(dossier)} chars")

    prompt = GEMMA_PROMPT_TEMPLATE.format(dossier=dossier)

    print(f"[sleep-bind] Calling {GEMMA_MODEL} via ollama (timeout {OLLAMA_TIMEOUT}s)...")
    gemma_raw = call_gemma(prompt)

    bound = None
    if gemma_raw:
        print(f"  Gemma response length: {len(gemma_raw)} chars")
        bound = extract_json(gemma_raw)
        if bound:
            print("  JSON parse: OK (first pass)")
        else:
            print("  JSON parse: FAILED first pass, trying fallback prompt...")
            gemma_raw2 = call_gemma(SIMPLE_PROMPT_TEMPLATE.format(dossier=dossier))
            if gemma_raw2:
                bound = extract_json(gemma_raw2)
                if bound:
                    print("  JSON parse: OK (fallback pass)")
                else:
                    print("  JSON parse: FAILED fallback — storing raw response")
    else:
        print("  [warn] Gemma returned no response")

    if not bound:
        bound = {
            "entities": [],
            "bindings": [],
            "poster_count": {},
            "summary": "PARSE_ERROR",
            "raw_gemma_response": gemma_raw or "",
        }

    # Ensure required keys exist
    for key in ("entities", "bindings", "poster_count", "summary"):
        if key not in bound:
            bound[key] = [] if key in ("entities", "bindings") else ({} if key == "poster_count" else "")

    bound["_provenance"] = {
        "builder": "build_sleep_bind:v2",
        "source_fingerprint": source_fingerprint(memory_dir),
        "memory_id": os.path.basename(os.path.dirname(os.path.abspath(memory_dir))),
    }
    bound["usable"] = bool(bound.get("entities") or bound.get("bindings")) \
        and bound.get("summary") != "PARSE_ERROR"

    out_path = os.path.join(memory_dir, "bound_memory.json")
    with open(out_path, "w") as f:
        json.dump(bound, f, indent=2, ensure_ascii=False)
    print(f"[sleep-bind] Saved: {out_path}")
    return bound


def self_test(memory_dir):
    """Run bind and verify PASS criteria."""
    print(f"[self-test] memory_dir = {memory_dir}")
    bound = run_bind(memory_dir)

    out_path = os.path.join(memory_dir, "bound_memory.json")
    passed = True

    if not os.path.exists(out_path):
        print("FAIL: bound_memory.json was not written")
        return False

    n_entities = len(bound.get("entities") or [])
    if n_entities < 1:
        print(f"FAIL: only {n_entities} entities (need >=1)")
        passed = False
    else:
        print(f"  entities: {n_entities} >= 1 OK")

    bindings = bound.get("bindings") or []
    print(f"  bindings: {len(bindings)} (empty is valid when evidence is ambiguous)")

    prov = bound.get("_provenance") or {}
    if prov.get("source_fingerprint") != source_fingerprint(memory_dir):
        print("FAIL: source fingerprint missing or stale")
        passed = False
    else:
        print("  source fingerprint: OK")

    if bound.get("summary") and bound["summary"] != "PARSE_ERROR":
        print(f"  summary: present OK")
    else:
        print(f"FAIL: summary missing or PARSE_ERROR")
        passed = False

    print()
    print("PASS" if passed else "FAIL")
    return passed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--self-test":
        # Default test walk
        mem_dir = (sys.argv[2] if len(sys.argv) > 2 else
                   os.path.join(os.path.dirname(__file__),
                                "..", "data", "walks",
                                "walk_outside_20260614", "memory"))
        mem_dir = os.path.abspath(mem_dir)
        ok = self_test(mem_dir)
        sys.exit(0 if ok else 1)
    else:
        mem_dir = os.path.abspath(sys.argv[1])
        if not os.path.isdir(mem_dir):
            print(f"Error: {mem_dir} is not a directory")
            sys.exit(1)
        run_bind(mem_dir)
