#!/usr/bin/env python3
"""Honesty tests for the EXPAND / injection layer. The whole point is that world
knowledge ENRICHES without fabricating or bleeding into personal claims, so these
test the guards, not just the happy path.

Run: PYTHONPATH=scripts .venv/bin/python -m pytest evaluation/test_inject_expand.py -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import inject_expand as ix


def fake_oracle(prompt: str) -> str:
    """Deterministic stand-in. Suggests one grounded + one HALLUCINATED referent,
    glosses Röntgen confidently, and returns UNKNOWN for a generic word."""
    if "STRICT fact-checker" in prompt:  # skeptical corroboration pass
        return "YES" if "Röntgen" in prompt else "NO"
    if "OWN CAMERA" in prompt:  # the personal-zone grounding summary
        return "You saw a plaque reading Wilhelm Conrad Röntgen, 1845-1923."
    if "JSON array" in prompt:
        # 'Apple Inc' is NOT in the evidence -> must be dropped by the grounding guard.
        return '["Wilhelm Conrad Röntgen", "Apple Inc", "street"]'
    if "Röntgen" in prompt:
        return "KIND: person\nCONF: 0.95\nGLOSS: A German physicist who discovered X-rays and won the first Nobel Prize in Physics (1901)."
    if "street" in prompt:
        return "UNKNOWN"
    return "UNKNOWN"


EVIDENCE = ["WILHELM CONRAD RÖNTGEN", "1845 - 1923", "Physik", "street sign"]


def test_two_zone_packet_shape():
    pkt = ix.expand(EVIDENCE, "who was the person on the plaque?", fake_oracle)
    assert set(pkt) == {"personal_evidence", "world_context"}
    assert pkt["personal_evidence"] == EVIDENCE
    assert all(w["tier"] == "world_context" for w in pkt["world_context"])


def test_grounding_drops_unseen_referent():
    # 'Apple Inc' was suggested by the oracle but never observed -> never expanded.
    pkt = ix.expand(EVIDENCE, "who was this?", fake_oracle)
    refs = [w["referent"] for w in pkt["world_context"]]
    assert not any("apple" in r.lower() for r in refs), "expanded a referent the user never saw"


def test_confident_or_silent_drops_unknown():
    # 'street' is in evidence but the oracle says UNKNOWN -> no fabricated gloss.
    pkt = ix.expand(EVIDENCE, "what is this?", fake_oracle)
    refs = [w["referent"].lower() for w in pkt["world_context"]]
    assert "street" not in refs


def test_expands_the_real_referent():
    pkt = ix.expand(EVIDENCE, "who was the person on the plaque?", fake_oracle)
    g = [w for w in pkt["world_context"] if "röntgen" in w["referent"].lower()]
    assert len(g) == 1
    assert "x-ray" in g[0]["gloss"].lower()
    assert g[0]["kind"] == "person" and g[0]["confidence"] >= 0.6


def test_compose_fences_world_from_personal():
    pkt = ix.expand(EVIDENCE, "who was the person on the plaque?", fake_oracle)
    out = ix.compose("The plaque reads Wilhelm Conrad Röntgen, 1845-1923.", pkt)
    # personal answer present, world knowledge present but in a SEPARATE, labelled zone
    assert "The plaque reads" in out
    assert "```world_context" in out
    assert "general knowledge, not from your memory" in out
    assert "X-rays" in out


def test_summarize_observed_is_personal_only():
    s = ix.summarize_observed(EVIDENCE, fake_oracle)
    assert s.startswith("You saw")
    # grounded in the observation, no invented world facts (e.g. "X-rays")
    assert "x-ray" not in s.lower()


def test_unknown_oracle_yields_personal_only():
    pkt = ix.expand(["a generic street"], "what is this?", lambda p: "UNKNOWN" if "GLOSS" in p else "[]")
    assert pkt["world_context"] == []
    assert ix.compose("It's a street.", pkt) == "It's a street."
