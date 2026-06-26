from __future__ import annotations

from trace_memory.adapters.live_eventlog import OPEN_SCENE_REFUSAL, answer_question, append_perception_observations


def _fake_scene_oracle(prompt: str) -> str:
    lowered = prompt.lower()
    if "first line exactly: yes or no" in lowered:
        return "YES" if "pringles" in lowered else "NO"
    if "pringles" in lowered:
        return (
            "KIND: product\n"
            "CONF: 0.94\n"
            "GLOSS: Pringles is a brand of stackable potato crisps."
        )
    return "UNKNOWN"


def _append_scene_frame(db_path, moment_id: str, t_seconds: float, memory_lines: list[str]) -> None:
    append_perception_observations(
        db_path,
        moment_id=moment_id,
        t_seconds=t_seconds,
        memory_text="\n".join(memory_lines),
        ocr_lines=[],
    )


def test_open_scene_answer_names_clear_objects_and_returns_two_zones(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    frames = [
        [
            "OBJECT | water bottle | blue bottle | desk | likely",
            "OBJECT | pringles can | flavour: sour cream and onion | desk | likely",
            "OBJECT | cereal box | cardboard cereal box | desk | likely",
        ],
        [
            "OBJECT | water bottle | blue bottle | desk | likely",
            "OBJECT | pringles can | flavour: sour cream and onion | desk | likely",
            "OBJECT | cereal box | cardboard cereal box | desk | likely",
        ],
        [
            "OBJECT | water bottle | blue bottle | desk | likely",
            "OBJECT | pringles can | flavour: sour cream and onion | desk | likely",
            "OBJECT | cereal box | cardboard cereal box | desk | likely",
        ],
    ]

    for index, memory_lines in enumerate(frames, start=1):
        _append_scene_frame(db_path, "scene", float(index), memory_lines)

    result = answer_question(
        "what did I see",
        db_path,
        world_knowledge_oracle=_fake_scene_oracle,
    )

    assert result.supported is True
    assert result.refused is False
    assert result.personal_evidence
    lowered = result.answer.lower()
    assert "water bottle" in lowered
    assert "pringles" in lowered
    assert "cereal box" in lowered
    assert "seen at" in lowered
    assert result.world_context.startswith("```world_context\n")
    assert "pringles is a brand of stackable potato crisps." in result.world_context.lower()


def test_open_scene_excludes_low_confidence_only_ghosts(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _append_scene_frame(
        db_path,
        "scene",
        1.0,
        ["OBJECT | bottle | ghost bottle | left edge | likely"],
    )

    result = answer_question("what's here", db_path)

    assert result.supported is True
    assert result.refused is True
    assert result.answer == OPEN_SCENE_REFUSAL
    assert "ghost bottle" not in result.answer.lower()


def test_open_scene_refuses_when_memory_is_empty(tmp_path) -> None:
    db_path = tmp_path / "events.db"

    result = answer_question("describe what I saw", db_path)

    assert result.supported is True
    assert result.refused is True
    assert result.answer == OPEN_SCENE_REFUSAL
    assert result.personal_evidence == ""
    assert result.world_context == ""
