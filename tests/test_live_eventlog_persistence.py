from __future__ import annotations

import scripts.trace_brain_server as brain
from trace_memory.adapters.sqlite_eventlog import SqliteEventLog


def test_live_eventlog_persists_objects_across_restart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    brain._LIVE.clear()

    brain._capture(
        {
            "moment_id": "live",
            "memory_text": "\n".join(
                [
                    "OBJECT | water bottle | blue plastic bottle | kitchen table | likely",
                    "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
                ]
            ),
        }
    )

    brain._LIVE.clear()

    brain._capture(
        {
            "moment_id": "live",
            "memory_text": "\n".join(
                [
                    "OBJECT | stairs | wooden staircase | hallway | likely",
                    "OBJECT | window | open glass window | living room wall | likely",
                ]
            ),
        }
    )

    log = SqliteEventLog(str(tmp_path / "live" / "events.db"))
    try:
        subjects = [observation.subject for observation in log.observations() if observation.kind == "object"]
    finally:
        log.close()

    assert subjects == ["water bottle", "pringles can", "stairs", "window"]

