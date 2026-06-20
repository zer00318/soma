from __future__ import annotations

from soma.application.binder import Binder, BindResult
from soma.application.grounded_recall import GroundedRecall
from soma.application.grounding_gate import REFUSAL_TEXT
from soma.domain.confidence import Confidence
from soma.domain.observation import Attribute, Observation
from soma.domain.provenance import Provenance
from soma.domain.query import Query

_CORPUS = "A blue backpack rests on the wooden desk in the office."


class _FakeReasoner:
    def __init__(self, canned: str) -> None:
        self._canned = canned

    def reason(self, _prompt: str) -> str:
        return self._canned


def _obs(t_ms: int, **attrs: str) -> Observation:
    return Observation(
        kind="object",
        subject="backpack",
        attributes=tuple(Attribute(name, value) for name, value in attrs.items()),
        t_ms=t_ms,
        spatial_anchor=None,
        confidence=Confidence(0.7),
        provenance=Provenance(event_id=f"e{t_ms}", source_channel="vlm", captured_at_ms=t_ms),
        refutation_cue=None,
    )


def _bound_memory() -> BindResult:
    return Binder().bind([_obs(1000, color="blue"), _obs(2000, color="blue")])


def _recall(canned: str) -> GroundedRecall:
    return GroundedRecall(
        reasoner=_FakeReasoner(canned),
        load_memory=lambda _ref: _bound_memory(),
        load_corpus=lambda _ref: _CORPUS,
    )


def test_grounded_answer_passes_with_citations() -> None:
    recall = _recall("The backpack color is blue.")

    answer = recall.answer(Query("What color is the backpack?"), "mem-ref")

    assert answer.text == "The backpack color is blue."
    node_ids = {c.node_id for c in answer.citations}
    assert node_ids == {"vlm@1000", "vlm@2000"}
    assert {c.t_ms for c in answer.citations} == {1000, 2000}


def test_fabricated_answer_is_refused_without_citations() -> None:
    recall = _recall("The leather satchel hung inside the crimson wardrobe upstairs.")

    answer = recall.answer(Query("What color is the backpack?"), "mem-ref")

    assert answer.text == REFUSAL_TEXT
    assert answer.citations == ()
