from __future__ import annotations

import scripts.trace_brain_server as brain
from trace_memory.adapters import live_eventlog
from trace_memory.adapters.live_eventlog import HONEST_REFUSAL


def _capture_pantry(moment_id: str = "live") -> dict[str, str]:
    return {
        "moment_id": moment_id,
        "memory_text": "\n".join(
            [
                "OBJECT | pringles can | flavour: sour cream and onion | pantry shelf | likely",
                "TEXT: Pringles | nutella",
            ]
        ),
    }


def _fake_pringles_oracle(prompt: str) -> str:
    lowered = prompt.lower()
    if "first line exactly: yes or no" in lowered:
        return "YES"
    if "pringles" in lowered:
        return (
            "KIND: product\n"
            "CONF: 0.94\n"
            "GLOSS: Pringles is a brand of stackable potato crisps."
        )
    return "UNKNOWN"


def test_seen_object_returns_personal_evidence_and_fenced_world_context(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    monkeypatch.setattr(brain, "_eventlog_world_knowledge_oracle", _fake_pringles_oracle)
    brain._LIVE.clear()

    brain._capture(_capture_pantry())

    result = brain._ask({"moment_id": "live", "question": "what flavour is the pringles"})

    assert result["source"] == "eventlog"
    assert result["refused"] is False
    assert result["personal_evidence"]
    assert result["world_context"]
    assert "sour cream and onion" in result["personal_evidence"].lower()
    assert result["world_context"].startswith("```world_context\n")
    assert "general knowledge, not from your memory" in result["world_context"]
    assert "pringles is a brand of stackable potato crisps." in result["world_context"].lower()
    assert result["answer"] == (
        result["personal_evidence"] + "\n\n" + result["world_context"]
    )
    assert "i saw pringles is a brand" not in result["answer"].lower()


def test_refusal_keeps_world_context_empty_for_unseen_subjects(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    monkeypatch.setattr(brain, "_eventlog_world_knowledge_oracle", _fake_pringles_oracle)
    brain._LIVE.clear()

    brain._capture(_capture_pantry())

    result = brain._ask({"moment_id": "live", "question": "how many nutella jars"})

    assert result["source"] == "eventlog"
    assert result["refused"] is True
    assert result["answer"] == HONEST_REFUSAL
    assert result["world_context"] == ""


def test_personal_evidence_still_works_when_inject_expand_is_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "TRACE_EVENTLOG", True)
    monkeypatch.setattr(live_eventlog, "_load_inject_expand", lambda: None)
    brain._LIVE.clear()

    brain._capture(_capture_pantry())

    result = brain._ask({"moment_id": "live", "question": "what flavour is the pringles"})

    assert result["source"] == "eventlog"
    assert result["refused"] is False
    assert result["personal_evidence"]
    assert result["world_context"] == ""
    assert result["answer"] == result["personal_evidence"]
