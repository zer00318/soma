"""M1 regression battery — ONE counting path (canonical spec I3).

The resolver reconciles binder-authored counts, attribute clustering, and the per-frame
floor. Locked behaviours:
  - verbatim world text ("poster reads PLATFORM 5 BUSES...") and OCR-helper rows NEVER
    become a count floor (the number-poisoning class),
  - identical multiples are rescued by a VLM sentence count even with adjectives in
    between ("Three black ceramic mugs"), reported hedged,
  - a binder count that disagrees with grounded evidence yields an honest RANGE, never a
    confident pick of one signal,
  - a single uncorroborated sighting is countable but never firm (the "snake" class),
  - count intent is a phrasing FAMILY ("Count the mugs for me", "number of X"), not ^how many.
All deterministic (no LLM).
"""
from __future__ import annotations

from trace_memory.brain.agent import TraceMemoryAgent, _count_subject
from trace_memory.store import TraceMemoryStore
from trace_memory.store import permanence


def _store(tmp_path, rows):
    store = TraceMemoryStore(str(tmp_path / "m1.sqlite3"))
    for i, row in enumerate(rows):
        text, meta = (row if isinstance(row, tuple) else (row, {}))
        node_type = meta.pop("node_type", "observation")
        base_meta = {"section_kind": "physical_object"}
        base_meta.update(meta)
        store.write_observation(text=text, t_ms=1000 + i * 100, source="phone_camera",
                                provenance={}, metadata=base_meta, node_type=node_type)
    return store


def _agent(store):
    return TraceMemoryAgent(store, restrict_sources=("phone_camera",))


def test_verbatim_poster_text_is_not_a_count(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | bus | small toy bus | shelf | likely",
        "A vintage transit poster on the wall reads PLATFORM 5 BUSES DEPART DAILY.",
    ])
    res = permanence.count_instances(store, "bus", sources=("phone_camera",), use_llm=False)
    assert res.floor == 0  # the 5 was quoted world text
    assert res.count == 1 and not res.firm  # single sighting -> hedged
    answer = _agent(store).answer("How many buses did I see?")
    assert answer.answer == "approximately 1" and answer.confidence <= 0.55


def test_ocr_helper_rows_never_floor(tmp_path):
    store = _store(tmp_path, [
        ("PLATFORM 5 BUSES DEPART DAILY", {"helper": "ocr"}),
        "OBJECT | bus | small toy bus | shelf | likely",
    ])
    res = permanence.count_instances(store, "bus", sources=("phone_camera",), use_llm=False)
    assert res.floor == 0


def test_identical_multiples_rescued_through_adjectives(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | mug | black ceramic mug | workbench | likely",
        "OBJECT | mug | black ceramic mug | workbench | likely",
        "Three black ceramic mugs sit in a row on the workbench.",
    ])
    res = permanence.count_instances(store, "mug", sources=("phone_camera",), use_llm=False)
    assert res.floor == 3 and res.count == 3 and not res.firm
    answer = _agent(store).answer("How many mugs are on the workbench?")
    assert answer.answer == "approximately 3" and answer.confidence <= 0.55


def test_binder_disagreement_yields_honest_range(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | keyboard | detected by on-device tracker | lower-left | likely",
        "OBJECT | keyboard | detected by on-device tracker | middle-center | likely",
        ("Counted 3 distinct keyboard instances, each a separately tracked object across frames.",
         {"node_type": "group_memory"}),
    ])
    answer = _agent(store).answer("How many keyboards do I have?")
    assert answer.answer == "between 1 and 3"
    assert answer.confidence <= 0.5 and not answer.refused


def test_binder_agreement_stays_firm(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | bottle | olive green glass bottle | shelf | likely",
        "OBJECT | bottle | white plastic bottle | shelf | likely",
        ("Counted 2 distinct bottle instances, each a separately tracked object across frames.",
         {"node_type": "group_memory"}),
    ])
    answer = _agent(store).answer("How many bottles are on the shelf?")
    assert answer.answer == "2" and answer.confidence == 0.8


def test_comma_list_labels_never_type_split(tmp_path):
    """REGRESSION (measured on the live desk store): in 'desk, keyboard, mouse' the word
    before 'keyboard' is another OBJECT, not a type modifier. Treating it as a type split
    one keyboard into per-frame-context phantoms that AGREED with the fragmented binder
    count -> firm-wrong. Comma-list reads carry no type signature."""
    store = _store(tmp_path, [
        "OBJECT | desk, keyboard, mouse, monitor",
        "OBJECT | keyboard | detected by on-device tracker | lower-left | likely",
        "OBJECT | monitor, keyboard, cup",
    ])
    res = permanence.count_instances(store, "keyboard", sources=("phone_camera",), use_llm=False)
    assert res.count == 1 and res.firm
    answer = _agent(store).answer("How many keyboards do I have?")
    assert answer.answer == "1" and answer.confidence == 0.8


def test_type_modifier_split_from_descriptor(tmp_path):
    """'c-clamp' vs 'bar clamp' in genuine descriptor phrases IS evidence of two objects."""
    store = _store(tmp_path, [
        "OBJECT | clamp | metal c-clamp | workbench edge | likely",
        "OBJECT | clamp | metal bar clamp | shelf | likely",
    ])
    res = permanence.count_instances(store, "clamp", sources=("phone_camera",), use_llm=False)
    assert res.count == 2


def test_count_intent_family_phrasings(tmp_path):
    assert _count_subject("Count the mugs for me.") == "mug"
    assert _count_subject("Tell me the number of clamps you saw.") == "clamp"
    assert _count_subject("What's the total of jars in the pantry?") == "jar"
    store = _store(tmp_path, [
        "OBJECT | mug | red ceramic mug | desk | likely",
        "OBJECT | mug | blue ceramic mug | desk | likely",
    ])
    answer = _agent(store).answer("Count the mugs for me.")
    assert answer.answer == "2" and answer.retrieval_mode.startswith("permanence:")
