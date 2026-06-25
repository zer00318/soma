from __future__ import annotations

import scripts.trace_brain_server as brain
from trace_memory.adapters.live_eventlog import HONEST_REFUSAL


def test_eventlog_answers_only_from_grounded_object_subjects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    brain._LIVE.clear()

    brain._capture(
        {
            "moment_id": "live",
            "memory_text": "\n".join(
                [
                    "OBJECT | water bottle | blue plastic bottle | counter | likely",
                    "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
                    "TEXT: nutella",
                ]
            ),
        }
    )

    nutella = brain._ask({"moment_id": "live", "question": "how many nutella jars"})
    assert nutella["source"] == "eventlog"
    assert nutella["refused"] is True
    assert nutella["answer"] == HONEST_REFUSAL

    water_exists = brain._ask({"moment_id": "live", "question": "is there a water bottle"})
    assert water_exists["source"] == "eventlog"
    assert water_exists["refused"] is False
    assert "water bottle" in water_exists["answer"].lower()

    water_count = brain._ask({"moment_id": "live", "question": "how many water bottles"})
    assert water_count["source"] == "eventlog"
    assert water_count["refused"] is False
    assert "1 water bottle" in water_count["answer"].lower()

    flavour = brain._ask({"moment_id": "live", "question": "what flavour is the pringles"})
    assert flavour["source"] == "eventlog"
    assert flavour["refused"] is False
    assert "sour cream and onion" in flavour["answer"].lower()

