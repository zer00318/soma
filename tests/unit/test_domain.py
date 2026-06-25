from __future__ import annotations

import pytest

from trace_memory.domain import (
    Attribute,
    Binding,
    Confidence,
    Entity,
    Observation,
    Provenance,
    Query,
)


def test_observation_accepts_open_vocabulary_text() -> None:
    provenance = Provenance("event-1", "vision_ocr", 1200)
    observation = Observation(
        kind="unseen-kind",
        subject="a user-defined subject",
        attributes=(Attribute("label", "free text"),),
        t_ms=1200,
        spatial_anchor=None,
        confidence=Confidence(0.72),
        provenance=provenance,
        refutation_cue="later OCR contradicted the label",
    )

    assert observation.subject == "a user-defined subject"


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_confidence_rejects_out_of_range_values(value: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Confidence(value)


def test_observation_requires_matching_provenance_time() -> None:
    with pytest.raises(ValueError, match="must match"):
        Observation(
            kind="object",
            subject="keys",
            attributes=(),
            t_ms=2,
            spatial_anchor=None,
            confidence=Confidence(1.0),
            provenance=Provenance("event-2", "vlm", 1),
        )


def test_query_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Query("  ")


def test_entity_and_binding_keep_open_vocabulary_with_provenance() -> None:
    entity = Entity("entity-1", "person-or-object", "blue thing near the desk")
    binding = Binding(
        binding_id="binding-1",
        subject_id=entity.entity_id,
        predicate="possibly_belongs_to",
        object_id=None,
        object_text="the visitor",
        confidence=Confidence(0.61),
        evidence=(Provenance("event-3", "ocr", 500),),
    )

    assert binding.is_usable(0.6)
    assert not binding.is_usable(0.7)


def test_binding_requires_exactly_one_target_and_evidence() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        Binding(
            "binding-2",
            "entity-1",
            "near",
            "entity-2",
            "also text",
            Confidence(0.5),
            (Provenance("event-4", "vlm", 10),),
        )
