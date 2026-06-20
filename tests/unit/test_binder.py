from __future__ import annotations

from soma.application.binder import Binder, BindResult
from soma.domain.confidence import Confidence
from soma.domain.observation import Attribute, Observation
from soma.domain.provenance import Provenance


def _obs(subject: str, t_ms: int, conf: float, **attrs: str) -> Observation:
    return Observation(
        kind="object",
        subject=subject,
        attributes=tuple(Attribute(name, value) for name, value in attrs.items()),
        t_ms=t_ms,
        spatial_anchor=None,
        confidence=Confidence(conf),
        provenance=Provenance(event_id=f"e{t_ms}", source_channel="vlm", captured_at_ms=t_ms),
        refutation_cue=None,
    )


def _binding(result: BindResult, predicate: str) -> object:
    return next((b for b in result.bindings if b.predicate == predicate), None)


def _refusal(result: BindResult, attribute: str) -> str | None:
    return next((r.reason for r in result.refused if r.attribute == attribute), None)


def test_repeated_consensus_binds_with_compounded_confidence() -> None:
    result = Binder().bind(
        [_obs("backpack", 1000, 0.6, color="blue"), _obs("backpack", 2000, 0.6, color="blue")]
    )

    assert [e.label for e in result.entities] == ["backpack"]
    bound = _binding(result, "color")
    assert bound is not None
    assert bound.object_text == "blue"
    # two independent 0.6 reads compound (noisy-OR) above either alone
    assert bound.confidence.value > 0.6
    assert len(bound.evidence) == 2


def test_single_sighting_is_refused_as_an_entity() -> None:
    result = Binder().bind([_obs("unicorn", 1000, 0.9, color="white")])

    assert result.entities == ()
    assert result.bindings == ()
    assert _refusal(result, "<entity>") == "insufficient_support"


def test_conflicting_values_bind_neither() -> None:
    result = Binder().bind(
        [
            _obs("bag", 1000, 0.8, color="blue"),
            _obs("bag", 2000, 0.8, color="blue"),
            _obs("bag", 3000, 0.8, color="black"),
            _obs("bag", 4000, 0.8, color="black"),
        ]
    )

    assert result.entities and result.entities[0].label == "bag"  # the entity exists...
    assert _binding(result, "color") is None  # ...but its colour is honestly unresolved
    assert _refusal(result, "color") == "ambiguous_conflict"


def test_repeated_but_each_unsure_is_refused_low_confidence() -> None:
    result = Binder(min_confidence=0.5).bind(
        [_obs("haze", 1000, 0.1, color="grey"), _obs("haze", 2000, 0.1, color="grey")]
    )

    assert _binding(result, "color") is None
    assert _refusal(result, "color") == "low_confidence"


def test_clear_winner_over_a_lone_competitor_still_binds() -> None:
    result = Binder().bind(
        [
            _obs("mug", 1000, 0.7, color="red"),
            _obs("mug", 2000, 0.7, color="red"),
            _obs("mug", 3000, 0.7, color="red"),
            _obs("mug", 4000, 0.3, color="orange"),
        ]
    )

    bound = _binding(result, "color")
    assert bound is not None and bound.object_text == "red"


def test_repeated_attribute_free_sightings_bind_as_presence() -> None:
    # A sign read twice carries no attribute, but its presence is a usable fact.
    result = Binder().bind([_obs("no entry sign", 1000, 0.7), _obs("no entry sign", 2000, 0.7)])

    presence = _binding(result, "present")
    assert presence is not None
    assert presence.object_text == "no entry sign"
    assert len(presence.evidence) == 2


def test_subject_spelling_variants_collapse_to_one_entity() -> None:
    result = Binder().bind(
        [_obs("Blue Bag", 1000, 0.7, color="blue"), _obs("blue   bag", 2000, 0.7, color="blue")]
    )

    assert len(result.entities) == 1
