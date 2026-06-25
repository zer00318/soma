from __future__ import annotations

from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.domain.confidence import Confidence
from trace_memory.domain.observation import Attribute, Observation
from trace_memory.domain.provenance import Provenance


def _observation(
    subject: str,
    t_ms: int,
    *,
    attributes: tuple[Attribute, ...] = (),
    spatial_anchor: str | None = None,
    refutation_cue: str | None = None,
) -> Observation:
    return Observation(
        kind="object",
        subject=subject,
        attributes=attributes,
        t_ms=t_ms,
        spatial_anchor=spatial_anchor,
        confidence=Confidence(0.5),
        provenance=Provenance(
            event_id=f"evt-{t_ms}",
            source_channel="webcam",
            captured_at_ms=t_ms,
        ),
        refutation_cue=refutation_cue,
    )


def test_append_then_read_round_trips_every_field() -> None:
    log = SqliteEventLog()
    obs = _observation(
        "red mug",
        1000,
        attributes=(Attribute("color", "red"), Attribute("location", "desk")),
        spatial_anchor="kitchen",
        refutation_cue="could be a bowl",
    )

    log.append(obs)
    stored = log.observations()

    assert stored == (obs,)


def test_log_preserves_append_order_not_payload_order() -> None:
    log = SqliteEventLog()
    for t in (3000, 1000, 2000):
        log.append(_observation("thing", t))

    subjects = [o.t_ms for o in log.observations()]

    assert subjects == [3000, 1000, 2000]


def test_empty_log_returns_empty_tuple() -> None:
    assert SqliteEventLog().observations() == ()


def test_events_persist_across_reopen(tmp_path: object) -> None:
    db = f"{tmp_path}/events.sqlite3"
    writer = SqliteEventLog(db)
    writer.append(_observation("persisted", 5000))
    writer.close()

    reopened = SqliteEventLog(db)

    assert reopened.observations() == (_observation("persisted", 5000),)


def test_optional_fields_round_trip_as_none() -> None:
    log = SqliteEventLog()
    log.append(_observation("bare", 7000))

    (stored,) = log.observations()

    assert stored.spatial_anchor is None
    assert stored.refutation_cue is None
    assert stored.attributes == ()
