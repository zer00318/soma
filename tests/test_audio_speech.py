from __future__ import annotations

from trace_memory.adapters.live_eventlog import SPEECH_REFUSAL, answer_question, append_perception_observations
from trace_memory.adapters.sqlite_eventlog import SqliteEventLog


def _append_speech(db_path, *, t_seconds: float = 12.0) -> None:
    append_perception_observations(
        db_path,
        moment_id="audio",
        t_seconds=t_seconds,
        memory_text='EVENT | nearby speech | transcript: "let\'s grab coffee at noon" | spoken nearby | likely',
        ocr_lines=[],
    )


def test_append_speech_observation_uses_audio_channel(tmp_path) -> None:
    db_path = tmp_path / "events.db"

    _append_speech(db_path)

    log = SqliteEventLog(str(db_path))
    try:
        observations = log.observations()
    finally:
        log.close()

    assert len(observations) == 1
    observation = observations[0]
    assert observation.kind == "speech"
    assert observation.subject == "speech"
    assert observation.provenance.source_channel == "audio"
    assert observation.attributes[0].name == "transcript"
    assert observation.attributes[0].value == "let's grab coffee at noon"


def test_what_was_said_quotes_transcript_with_time(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _append_speech(db_path)

    result = answer_question("what was said", db_path)

    assert result.supported is True
    assert result.refused is False
    assert "let's grab coffee at noon" in result.answer.lower()
    assert "12.0s" in result.answer.lower()


def test_did_anyone_mention_coffee_returns_grounded_yes(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _append_speech(db_path)

    result = answer_question("did anyone mention coffee", db_path)

    assert result.supported is True
    assert result.refused is False
    assert result.answer.lower().startswith("yes.")
    assert "coffee" in result.answer.lower()
    assert "12.0s" in result.answer.lower()


def test_did_anyone_mention_pizza_returns_honest_no(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    _append_speech(db_path)

    result = answer_question("did anyone mention pizza", db_path)

    assert result.supported is True
    assert result.refused is False
    assert result.answer.lower().startswith("no.")
    assert '"pizza"' in result.answer.lower()


def test_what_was_said_refuses_without_speech(tmp_path) -> None:
    db_path = tmp_path / "events.db"

    result = answer_question("what was said", db_path)

    assert result.supported is True
    assert result.refused is True
    assert result.answer == SPEECH_REFUSAL


def test_kind_equals_event_subject_equals_speech_is_ingested(tmp_path) -> None:
    db_path = tmp_path / "events.db"

    append_perception_observations(
        db_path,
        moment_id="audio",
        t_seconds=3.0,
        memory_text='kind=event subject=speech transcript="trace said hello"',
        ocr_lines=[],
    )

    result = answer_question("what did I hear", db_path)

    assert result.refused is False
    assert "trace said hello" in result.answer.lower()
    assert "3.0s" in result.answer.lower()
