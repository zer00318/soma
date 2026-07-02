"""M0 regression battery — the unicorn breach.

The count fastpath must (a) run BEHIND the subject-grounding gate, (b) count only the noun
phrase actually being counted, never an incidental location noun in the question, and
(c) handle irregular plurals. A count question about an object that was never observed must
NEVER produce a confident count. Deterministic (reasoner='heuristic', use_llm=False path).
"""
from __future__ import annotations

import pytest

from trace_memory.brain.agent import TraceMemoryAgent, _count_subject
from trace_memory.store import TraceMemoryStore


@pytest.fixture()
def desk_store(tmp_path):
    """A realistic desk capture: same wire shapes the phone emits via trace_hub."""
    store = TraceMemoryStore(str(tmp_path / "desk.sqlite3"))
    rows = [
        ("OBJECT | desk, keyboard, mouse, monitor", "detector"),
        ("OBJECT | keyboard | detected by on-device tracker | lower-left of frame | likely", "detector"),
        ("OBJECT | mouse | detected by on-device tracker | lower-right of frame | likely", "detector"),
        ("OBJECT | mug | red ceramic mug | desk | likely", "vlm_object"),
        ("OBJECT | mug | blue ceramic mug | desk | likely", "vlm_object"),
    ]
    for i, (text, helper) in enumerate(rows):
        store.write_observation(
            text=text, t_ms=1000 + i * 1000, source="phone_camera",
            provenance={"source": "test"},
            metadata={"helper": helper, "helper_prompt": helper, "section_kind": "physical_object"},
        )
    return store


@pytest.fixture()
def agent(desk_store):
    # Default heuristic reasoner: any fall-through refuses. The battery asserts the count
    # fastpath itself never fabricates — no LLM required.
    return TraceMemoryAgent(desk_store, restrict_sources=("phone_camera",))


ABSENT_COUNT_BATTERY = [
    "How many unicorns are on the desk?",
    "How many flamingos were near the keyboard?",
    "How many dogs are under the desk?",
    "How many parrots did you see by the monitor?",
    "How many trumpets are on the desk?",
    "How many cats were sitting on the keyboard?",
    "How many snakes are behind the monitor?",
    "How many candles were next to the mouse?",
    "How many pizzas did I have on the desk?",
    "How many geese were near the mug?",
]


@pytest.mark.parametrize("question", ABSENT_COUNT_BATTERY)
def test_count_of_absent_never_confident(agent, question):
    answer = agent.answer(question)
    # The moat: an unobserved object may be refused, but never confidently counted.
    assert answer.refused, f"{question!r} -> {answer.answer!r} @ {answer.confidence}"
    assert answer.confidence <= 0.5


def test_count_of_present_still_counts(agent):
    answer = agent.answer("How many mugs are on the desk?")
    assert not answer.refused
    assert answer.answer == "2"  # red + blue attribute-conflict split
    assert answer.retrieval_mode.startswith("permanence:")


def test_irregular_plural_binds_to_right_label(agent):
    answer = agent.answer("How many mice are on the desk?")
    assert not answer.refused
    # It counts the MOUSE (1 tracked instance), not the desk.
    assert answer.answer == "1"
    assert any("mouse" in str(r.get("text", "")).lower() for r in answer.evidence_chain)


def test_count_subject_extraction():
    assert _count_subject("How many mugs are on the workbench?") == "mug"
    assert _count_subject("How many nutella jars were there in total?") == "nutella jar"
    assert _count_subject("How many mice did you see?") == "mouse"
    assert _count_subject("How many buses did I see?") == "bus"
    # M1 widened intent to a phrasing family: imperative counting now routes too.
    assert _count_subject("Count the mugs for me.") == "mug"
    # No count intent at all -> empty (fastpath falls through).
    assert _count_subject("Where is the mug?") == ""


@pytest.mark.parametrize("junk", ["??????", "a", "how many", "   ", "!!!"])
def test_no_content_tokens_refuse_specifically(agent, junk):
    """M7 hammer regression: junk input bypassed the grounding gate (empty subject) and the
    reasoner narrated random evidence at 0.7. No subject -> structural refusal."""
    answer = agent.answer(junk)
    assert answer.refused and answer.confidence <= 0.2


def test_existence_requires_full_subject_phrase(agent):
    """Canonical battery AB02 regression: 'soldering iron' must not exist just because a
    'cast iron kettlebell' contains 'iron' — existence needs ALL subject tokens."""
    answer = agent.answer("Is there a soldering iron on the desk?")
    assert "no record" in answer.answer.lower()
    assert answer.retrieval_mode == "existence:deterministic-absent"
    present = agent.answer("Is there a keyboard on the desk?")
    assert present.retrieval_mode != "existence:deterministic-absent"


def test_temporal_order_is_deterministic(desk_store):
    """Canonical battery TP05 regression: before/after answered from timestamps, not the LLM
    (which inverts relative order roughly at chance)."""
    desk_store.write_observation(
        text="OBJECT | banana | yellow banana | desk | likely", t_ms=9000,
        source="phone_camera", provenance={},
        metadata={"helper": "vlm_object", "section_kind": "physical_object"})
    agent = TraceMemoryAgent(desk_store, restrict_sources=("phone_camera",))
    a = agent.answer("Did I see the banana before or after the mouse?")
    assert "after" in a.answer and a.retrieval_mode == "temporal:deterministic-order"
    b = agent.answer("Which came first, the mouse or the banana?")
    assert "before" in b.answer


def test_assertion_of_sight_arms_the_gaslight_guard():
    """Canonical battery GA02 regression: 'I know you saw X' is a planted premise."""
    from trace_memory.brain.agent import _has_planted_premise
    assert _has_planted_premise("I know you saw my red toolbox — where did I put it?")
    assert _has_planted_premise("You must have seen the golden trophy.")
    assert not _has_planted_premise("Where did I put my toolbox?")
