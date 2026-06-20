from __future__ import annotations

import json
from pathlib import Path

from soma.demo import bound_memory_to_dict, build_bound_memory, corpus_from_observations
from soma.domain.confidence import Confidence
from soma.domain.observation import Attribute, Observation
from soma.domain.provenance import Provenance


def _obs(subject: str, t_ms: int, value: str) -> Observation:
    return Observation(
        kind="object",
        subject=subject,
        attributes=(Attribute("color", value),),
        t_ms=t_ms,
        spatial_anchor=None,
        confidence=Confidence(0.7),
        provenance=Provenance(event_id=f"e{t_ms}", source_channel="ocr", captured_at_ms=t_ms),
        refutation_cue=None,
    )


def test_corpus_lowercases_subjects_and_attribute_values() -> None:
    corpus = corpus_from_observations([_obs("Backpack", 1000, "Blue")])
    assert "backpack" in corpus
    assert "blue" in corpus


def test_build_bound_memory_from_a_keyframe_file_yields_usable_bindings(tmp_path: Path) -> None:
    # Two keyframes both reading the same sign -> a bound, usable text fact.
    (tmp_path / "kf_memory.json").write_text(
        json.dumps(
            [
                {"t": 1.0, "frame": "a.jpg", "caption": "a sign", "ocr": ["NO ENTRY"]},
                {"t": 2.0, "frame": "b.jpg", "caption": "a sign", "ocr": ["NO ENTRY"]},
            ]
        ),
        encoding="utf-8",
    )

    result, corpus = build_bound_memory(str(tmp_path))
    payload = bound_memory_to_dict(result)

    assert payload["usable"] is True
    assert payload["counts"]["bindings"] >= 1  # type: ignore[index]
    assert "no entry" in corpus


def test_bound_memory_serialization_round_trips_to_json(tmp_path: Path) -> None:
    (tmp_path / "kf_memory.json").write_text(
        json.dumps([{"t": 1.0, "frame": "a.jpg", "caption": "x", "ocr": ["EXIT"]}]),
        encoding="utf-8",
    )
    result, _ = build_bound_memory(str(tmp_path))
    # one sighting -> refused as an entity; the artifact stays serializable and honest
    payload = bound_memory_to_dict(result)
    assert json.loads(json.dumps(payload))["usable"] is False
