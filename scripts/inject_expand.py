#!/usr/bin/env python3
"""inject_expand.py — the INJECTION / EXPAND layer (spec I2 EXPAND + I3 TIER + I4
COMPILE). This is the "Prompt" in Context -> Prompt -> Answer: it turns remembered
perception into UNDERSTANDING by attaching fenced, sourced WORLD knowledge to the
referents the helpers actually observed — a storefront, a plaque, a poster becomes
"what it IS / what it's known for", grounded to what was seen.

Two hard contracts (from ops/CONTEXT_ENGINE_PHASE2B_INJECTION_LAYER):
  - TIER: every fact is personal_evidence (a helper observed it, citable) OR
    world_context (EXPAND retrieved it about a referent). The two never merge — a
    world fact NEVER becomes a personal claim ("you saw X", "you wrote X").
  - GROUNDED EXPANSION: EXPAND may only explain a referent that actually appears in
    the observed evidence. It never invents a referent the user did not see.

Privacy by construction: the world oracle is the ON-DEVICE LLM (gemma). Only the
already-redacted typed referent string is shown to it; ZERO network egress. This is
the strongest form of the spec's local-only EXPAND mode. A confident-or-silent
oracle (replies UNKNOWN when unsure) keeps it honest: unknown referents stay
unexpanded rather than fabricated.

LLM interface: a callable `llm(prompt: str) -> str` (same shape consensus_recall
uses), so this is unit-testable with a fake oracle and runnable with real gemma.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

KINDS = ("person", "place", "org", "product", "work", "event", "term")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _evidence_blob(evidence: list[str]) -> str:
    return _norm(" \n ".join(str(e) for e in evidence))


def _seen_in_evidence(referent: str, blob: str) -> bool:
    """A referent is grounded only if it (or its longest token) was actually
    observed. Guards against the oracle inventing a referent the user never saw."""
    r = _norm(referent)
    if not r:
        return False
    if r in blob:
        return True
    toks = [t for t in r.split() if len(t) >= 4]
    # Every long token present (handles "RÖNTGEN" referent vs "WILHELM CONRAD
    # RÖNTGEN" evidence, and word-order differences) — but require at least one
    # distinctive token so generic words can't slip through.
    return bool(toks) and all(t in blob for t in toks)


_SELECT_PROMPT = (
    "From the things a user ACTUALLY SAW through their own camera, list up to {n} "
    "proper-noun referents (specific real-world people, places, organizations, "
    "products, works, or events) that are RELEVANT to the question. Only include a "
    "referent if it literally appears in the observations. Ignore generic words "
    "(street, sign, store, building). Output ONLY a JSON array of strings.\n\n"
    "QUESTION: {q}\n\nOBSERVATIONS:\n{ev}\n\nJSON array:"
)

_GLOSS_PROMPT = (
    "You are an offline world-knowledge oracle. A user physically saw something that "
    'reads / shows: "{ref}". In ONE sentence say what this most likely refers to in '
    "the real world and what it is known for. Rules: answer ONLY if you are "
    "genuinely confident; if you do not recognize it, or it is a generic word, reply "
    "exactly UNKNOWN. Never invent. Format EXACTLY:\n"
    "KIND: <person|place|org|product|work|event|term>\n"
    "CONF: <0.0-1.0>\n"
    "GLOSS: <one factual sentence, or UNKNOWN>"
)


def _parse_json_array(text: str) -> list[str]:
    m = re.search(r"\[.*\]", text or "", re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return []
    return [str(x).strip() for x in arr if isinstance(x, (str, int, float)) and str(x).strip()]


def _parse_gloss(text: str) -> Optional[dict]:
    text = text or ""
    if re.search(r"\bUNKNOWN\b", text) and "GLOSS:" not in text:
        return None
    kind = (re.search(r"KIND:\s*([A-Za-z]+)", text) or [None, ""])[1].lower().strip()
    conf_m = re.search(r"CONF:\s*([0-9]*\.?[0-9]+)", text)
    gloss_m = re.search(r"GLOSS:\s*(.+)", text, re.DOTALL)
    gloss = (gloss_m.group(1).strip() if gloss_m else "").splitlines()[0].strip() if gloss_m else ""
    if not gloss or re.fullmatch(r"UNKNOWN\.?", gloss, re.IGNORECASE):
        return None
    if kind not in KINDS:
        kind = "term"
    try:
        conf = float(conf_m.group(1)) if conf_m else 0.5
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    return {"kind": kind, "confidence": round(conf, 2), "gloss": gloss}


def select_referents(evidence: list[str], question: str, llm: Callable[[str], str],
                     max_referents: int = 3) -> list[str]:
    """Salient observed referents relevant to the question, GROUNDED to evidence."""
    ev = "\n".join(f"- {e}" for e in evidence if str(e).strip())
    if not ev:
        return []
    raw = _parse_json_array(llm(_SELECT_PROMPT.format(n=max_referents, q=question, ev=ev)))
    blob = _evidence_blob(evidence)
    out, seen = [], set()
    for r in raw:
        key = _norm(r)
        if key and key not in seen and _seen_in_evidence(r, blob):
            out.append(r)
            seen.add(key)
        if len(out) >= max_referents:
            break
    return out


_SUMMARY_PROMPT = (
    "In ONE plain sentence, describe what the user's OWN CAMERA observed, using ONLY "
    "these observations. Do NOT add outside facts, history, or names that are not "
    'present. Begin with "You saw" or "You were".\n\nOBSERVATIONS:\n{ev}\n\nOne sentence:'
)


def summarize_observed(evidence: list[str], llm: Callable[[str], str]) -> str:
    """A one-sentence PERSONAL-ZONE grounding of what the camera saw — strictly from
    the observations, no world knowledge. Used to back the world_context when the
    base brain over-refused (so the two zones stay coherent and honest)."""
    ev = "\n".join(f"- {e}" for e in evidence if str(e).strip())
    if not ev:
        return ""
    out = [ln.strip() for ln in (llm(_SUMMARY_PROMPT.format(ev=ev)) or "").splitlines() if ln.strip()]
    return out[0] if out else ""


_VERIFY_PROMPT = (
    'You are a STRICT fact-checker. A user saw text that reads: "{ref}". Is this the name of a '
    "REAL, specific, widely-documented real-world entity (a particular person, place, organization, "
    "product, work, or event) that you can identify with HIGH CONFIDENCE from general knowledge? Be "
    "skeptical: if it is generic, unfamiliar, or could plausibly be invented, answer NO. A made-up "
    "but real-sounding company name must be NO. First line EXACTLY: YES or NO."
)


def _corroborated(referent: str, llm: Callable[[str], str]) -> bool:
    """Refute-by-default second pass. gemma confidently FABRICATES a plausible gloss for an
    unknown-but-real-looking name (audit: 'ZLORPTECH SYSTEMS GMBH' at conf 0.95) — self-reported
    confidence is worthless. A fresh skeptical existence check is the real gate: real entities
    (McDonald's, Röntgen) survive; invented/generic ones get refuted."""
    out = (llm(_VERIFY_PROMPT.format(ref=referent)) or "").strip()
    first = out.splitlines()[0].strip().upper() if out else ""
    return first.startswith("YES")


def world_gloss(referent: str, llm: Callable[[str], str]) -> Optional[dict]:
    """One fenced world-knowledge fact about a referent, or None (confident-or-silent)."""
    parsed = _parse_gloss(llm(_GLOSS_PROMPT.format(ref=referent)))
    if parsed is None:
        return None
    if not _corroborated(referent, llm):  # skeptical pass kills confident fabrications
        return None
    parsed.update({"referent": referent, "tier": "world_context"})
    return parsed


def expand(evidence: list[str], question: str, llm: Callable[[str], str],
           max_referents: int = 3) -> dict:
    """I2+I3+I4: the two-zone evidence packet.

    Returns {personal_evidence: [...verbatim observed...],
             world_context: [{referent, kind, confidence, gloss, tier}...]}.
    world_context explains referents; it is NEVER a personal claim.
    """
    referents = select_referents(evidence, question, llm, max_referents)
    world: list[dict] = []
    for r in referents:
        g = world_gloss(r, llm)
        if g is not None:
            world.append(g)
    return {
        "personal_evidence": [str(e) for e in evidence if str(e).strip()],
        "world_context": world,
    }


def compose(personal_answer: str, packet: dict) -> str:
    """Render the two-zone answer deterministically — the grounded personal answer,
    then a physically FENCED world-knowledge note. Fencing (not prose-blending) is
    what guarantees a world fact is never read as a personal observation."""
    out = (personal_answer or "").strip()
    world = packet.get("world_context") or []
    if not world:
        return out
    lines = []
    for w in world:
        hedge = "" if w.get("confidence", 0) >= 0.6 else " (likely)"
        lines.append(f"• {w['referent']}{hedge}: {w['gloss']}")
    note = (
        "```world_context\n"
        "About what you saw (general knowledge, not from your memory):\n"
        + "\n".join(lines)
        + "\n```"
    )
    return (out + "\n\n" + note).strip() if out else note


if __name__ == "__main__":  # tiny manual demo with real gemma
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ask_home  # for _ollama

    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--evidence", nargs="+", required=True)
    ap.add_argument("--model", default="gemma3:12b-it-qat")
    args = ap.parse_args()
    oracle = lambda p: ask_home._ollama(p, args.model, "http://127.0.0.1:11434", 120)
    pkt = expand(args.evidence, args.question, oracle)
    print(json.dumps(pkt, ensure_ascii=False, indent=2))
    print("\n--- composed ---\n" + compose("(personal answer would go here)", pkt))
