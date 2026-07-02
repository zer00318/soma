"""Regression spec for multi-object permanence (scripts/permanence.py).

These lock the behaviours that make counting honest on REAL capture noise, all on the
deterministic (no-LLM) path so they run offline in CI:
  - re-observations of one object across frames collapse to ONE instance
  - genuinely different objects (incompatible colour/material) stay separate
  - colour lexical drift (teal/cyan/green) does NOT split one object
  - the VLM's own per-frame count is a floor for identical-looking multiples
  - '#N label' instance indices, leading-zero garble, and >20 OCR noise are NOT counts
"""
from __future__ import annotations

from trace_memory.store import TraceMemoryStore
from trace_memory.store import permanence


def _store(tmp_path, lines):
    store = TraceMemoryStore(tmp_path / "perm.sqlite3")
    for i, line in enumerate(lines):
        store.write_observation(text=line, t_ms=1000 + i * 100, source="phone_camera",
                                provenance={}, metadata={"section_kind": "physical_object"})
    return store


def _count(store, subject):
    return permanence.count_instances(store, subject, sources=("phone_camera",), use_llm=False)


def test_reobservations_collapse_to_one(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | water bottle | blue plastic bottle | counter | likely",
        "OBJECT | water bottle | blue plastic bottle | counter | likely",
        "OBJECT | water bottle | blue bottle | table | likely",
    ])
    assert _count(store, "water bottle").count == 1
    store.close()


def test_incompatible_attributes_stay_separate(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | water bottle | blue plastic bottle | counter | likely",
        "OBJECT | water bottle | clear glass bottle | shelf | likely",
        "OBJECT | water bottle | silver metal bottle | desk | likely",
    ])
    assert _count(store, "water bottle").count == 3
    store.close()


def test_colour_drift_does_not_split(tmp_path):
    store = _store(tmp_path, [
        "OBJECT | mug | teal ceramic mug | bench | likely",
        "OBJECT | mug | cyan mug | bench | likely",
        "OBJECT | mug | green cup | bench | likely",
    ])
    assert _count(store, "mug").count == 1
    store.close()


def test_per_frame_count_is_a_floor_for_identical_multiples(tmp_path):
    # Five identical jars read the same collapse to one cluster, but a frame said "5 jar".
    store = _store(tmp_path, [
        "OBJECT | jar | brown glass jar | shelf | likely",
        "OBJECT | jar | brown glass jar | shelf | likely",
        "INVENTORY TYPE (derived): 1 bag, 5 jar, 1 charger, 1 blanket",
    ])
    res = _count(store, "jar")
    assert res.count == 5
    assert res.floor == 5
    store.close()


def test_instance_index_is_not_a_count(tmp_path):
    # '#8 jar' is the 8th enumerated instance, not eight jars.
    store = _store(tmp_path, [
        'INSTANCES:\n  #0 phone "Smartphone" colour=Black\n  #8 jar "Nutella jar" colour=Brown',
    ])
    res = _count(store, "jar")
    assert res.floor == 0
    store.close()


def test_leading_zero_and_ocr_noise_rejected(tmp_path):
    store = _store(tmp_path, [
        'OCR: Bartle PESTOR / nutelld sume 52 nutella / 09 nutella',
    ])
    res = _count(store, "nutella")
    assert res.floor == 0
    store.close()


def test_absent_subject_counts_zero(tmp_path):
    store = _store(tmp_path, ["OBJECT | lamp | black desk lamp | desk | likely"])
    assert _count(store, "printer").count == 0
    store.close()
