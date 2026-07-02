"""Acceptance spec for the INJECT binder.

These are the founder-verified ground-truth behaviors on the real desk capture
(data/phone_captures/live/kf_memory.json). They double as:
  1. the regression gate (CI / the autonomous worker must keep these green), and
  2. the executable spec the local-LLM workers build toward.

Each test maps to a real question the founder asked, with the real answer.
A change that breaks one of these is a regression no matter how good it looks.
"""
from __future__ import annotations

import pytest

from scripts.inject_structure import build_scene


def _desk_records():
    """Hand-authored desk-scene capture (the founder-verified ground truth), encoded
    INLINE so the test owns its data — the live brain re-perceives and overwrites
    data/phone_captures/live/kf_memory.json, so a file fixture is non-deterministic.
    Each record matches the real perception schema {t, caption, ocr, source}."""
    recs = []
    t = 0.0
    # 8 frames: Nutella jars (-> high) + pesto jar object, with product OCR (no screen
    # device in these frames, so OCR stays world-text, not quarantined).
    for i in range(8):
        recs.append({
            "t": t, "frame": f"f{i}", "source": "native_vision",
            "caption": ("OBJECT | 3 jars of Nutella (brown glass jar with red label)\n"
                        "OBJECT | jar labelled Pesto"),
            "ocr": ["PESTO Barilla 195g con peperoncino", "Nutella"],
        })
        t += 1.0
    # 2 frames: rings, two phrasings -> must MERGE to >= medium.
    recs.append({"t": t, "frame": "f8", "source": "native_vision",
                 "caption": "OBJECT | 3 rings (one silver, one green and white, one gold)",
                 "ocr": []}); t += 1.0
    recs.append({"t": t, "frame": "f9", "source": "native_vision",
                 "caption": "OBJECT | Two rings", "ocr": []}); t += 1.0
    # 2 frames: physical laptop (must survive; only screen CONTENT is quarantined).
    for i in range(2):
        recs.append({"t": t, "frame": f"f{10+i}", "source": "native_vision",
                     "caption": "OBJECT | silver laptop with a blue light on its side",
                     "ocr": []}); t += 1.0
    # 2 frames: the tablecloth TRAP — a surface qualifier that must be stripped from the
    # spoon's display name (there is no tablecloth).
    for i in range(2):
        recs.append({"t": t, "frame": f"f{12+i}", "source": "native_vision",
                     "caption": "OBJECT | silver spoon resting on a grey tablecloth",
                     "ocr": []}); t += 1.0
    return recs


@pytest.fixture(scope="module")
def scene():
    return build_scene(_desk_records())


def _objs(scene, *, min_conf=("medium", "high")):
    return [o for o in scene["objects"] if o["confidence"] in min_conf]


def _has_key(scene, word, *, min_conf=("medium", "high")):
    return any(word in o["merge_key"] for o in _objs(scene, min_conf=min_conf))


# --- presence: things that ARE there -------------------------------------- #

def test_nutella_jars_high_confidence(scene):
    """5 Nutella jars across many frames -> the strongest signal in the scene."""
    nutella = [o for o in scene["objects"] if "nutella" in o["merge_key"]]
    assert nutella, "Nutella jars must be detected"
    assert any(o["confidence"] == "high" for o in nutella), \
        "Nutella seen in many frames must reach HIGH confidence"


def test_rings_merged_to_at_least_medium(scene):
    """'3 rings (one silver...)' + 'Two rings' must MERGE, not split below threshold."""
    assert _has_key(scene, "ring"), \
        "rings must merge across descriptions to >= medium confidence"


def test_pesto_is_present(scene):
    """Pesto is real (founder: 'con peperoncino'). It must surface as either a
    physical object OR a recurring OCR label — refusing 'is there pesto' is wrong."""
    as_object = _has_key(scene, "pesto")
    as_ocr = any("pesto" in e["text"].lower() for e in scene.get("ocr_entities", []))
    assert as_object or as_ocr, "pesto must be present via object or OCR consensus"


def test_laptop_device_not_dropped_as_screen(scene):
    """The physical laptop is a real object. Only its SCREEN CONTENT should be
    quarantined — the device itself must remain answerable."""
    assert _has_key(scene, "laptop"), \
        "the physical laptop must survive as an object (only screen content is quarantined)"


# --- absence: things that are NOT there (hallucination guards) ------------- #

def test_no_tablecloth_hallucination(scene):
    """Founder: there is no tablecloth. No asserted object NAME may claim one —
    a surface qualifier ('spoon resting on a grey tablecloth') must be stripped."""
    for o in _objs(scene):
        assert "tablecloth" not in o["name"].lower(), \
            f"tablecloth is a hallucination; leaked via: {o['name']!r}"


def test_no_pringles_hallucination(scene):
    """Founder: no Pringles in this capture."""
    assert not _has_key(scene, "pringles", min_conf=("medium", "high")), \
        "Pringles is not in this capture"


def test_no_cottage_cheese_hallucination(scene):
    """Founder: no cottage cheese."""
    joined = " ".join(o["name"].lower() for o in _objs(scene))
    assert "cottage cheese" not in joined and "hüttenkäse" not in joined, \
        "cottage cheese is a hallucination"


# --- structural invariants ------------------------------------------------ #

def test_scene_has_expected_shape(scene):
    for key in ("objects", "ocr_entities", "dropped", "total_frames"):
        assert key in scene, f"scene missing key: {key}"
    for o in scene["objects"]:
        assert {"name", "merge_key", "frames_seen", "confidence"} <= set(o)


def test_confidence_monotonic_with_frames(scene):
    """More corroborating frames must never yield LOWER confidence."""
    rank = {"low": 0, "medium": 1, "high": 2}
    objs = sorted(scene["objects"], key=lambda o: o["frames_seen"])
    for a, b in zip(objs, objs[1:]):
        if b["frames_seen"] > a["frames_seen"]:
            assert rank[b["confidence"]] >= rank[a["confidence"]], \
                f"{b['name']} ({b['frames_seen']}f) < {a['name']} ({a['frames_seen']}f) in confidence"
