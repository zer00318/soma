from __future__ import annotations

from trace_memory.adapters.live_eventlog import answer_question
from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.application.entity_binder import bind_entities
from trace_memory.domain.confidence import Confidence
from trace_memory.domain.observation import Attribute, Observation
from trace_memory.domain.provenance import Provenance


def _observation(
    subject: str,
    t_ms: int,
    *,
    spatial_anchor: str | None = None,
    detail: str = "visible object",
) -> Observation:
    return Observation(
        kind="object",
        subject=subject,
        attributes=(Attribute("detail", detail),),
        t_ms=t_ms,
        spatial_anchor=spatial_anchor,
        confidence=Confidence(0.72),
        provenance=Provenance(
            event_id=f"evt-{subject}-{t_ms}-{spatial_anchor or 'none'}",
            source_channel="vlm",
            captured_at_ms=t_ms,
        ),
    )


def test_bind_entities_counts_two_distinct_anchors_not_frames() -> None:
    observations = (
        _observation("bottle", 1000, spatial_anchor="left shelf", detail="blue bottle"),
        _observation("bottles", 1200, spatial_anchor="left shelf", detail="blue bottle"),
        _observation("water bottle", 1500, spatial_anchor="left shelf", detail="blue bottle"),
        _observation("bottle", 1800, spatial_anchor="left shelf", detail="blue bottle"),
        _observation("bottle", 5000, spatial_anchor="right shelf", detail="label: club soda"),
        _observation("bottle", 5200, spatial_anchor="right shelf", detail="label: club soda"),
        _observation("bottle", 5600, spatial_anchor="right shelf", detail="label: club soda"),
        _observation("bottle", 6000, spatial_anchor="right shelf", detail="label: club soda"),
    )

    [entity] = bind_entities(observations)

    assert entity.subject == "bottle"
    assert entity.count == 2
    assert entity.frames_seen == 8
    assert entity.confidence == "high"
    assert entity.spatial_anchors == frozenset({"left shelf", "right shelf"})
    assert entity.attributes == (
        Attribute("detail", "blue bottle"),
        Attribute("detail", "label: club soda"),
    )


def test_bind_entities_keeps_same_anchor_at_count_one() -> None:
    observations = tuple(
        _observation("bottle", 1000 + (index * 300), spatial_anchor="table edge", detail="green bottle")
        for index in range(5)
    )

    [entity] = bind_entities(observations)

    assert entity.count == 1
    assert entity.frames_seen == 5
    assert entity.spatial_anchors == frozenset({"table edge"})


def test_singleton_subject_stays_low_confidence_and_hedges_count_answer(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    log = SqliteEventLog(str(db_path))
    try:
        log.append(_observation("bottle", 1000))
    finally:
        log.close()

    [entity] = bind_entities((_observation("bottle", 1000),))
    answer = answer_question("how many bottles", db_path)

    assert entity.confidence == "low"
    assert answer.refused is False
    assert "at least 1 bottle" in answer.answer.lower()
    assert "can't reliably count it yet" in answer.answer.lower()
