from __future__ import annotations

import json
from pathlib import Path

from soma.adapters.legacy_channels import (
    load_observations,
    observations_from_entity_capture,
    observations_from_keyframes,
)


def test_keyframe_ocr_becomes_text_observation() -> None:
    rows = [
        {
            "t": 23.5,
            "frame": "frame_000705.jpg",
            "caption": "a sign",
            "ocr": ["1 SOMA CON", "EXIT"],
        }
    ]
    observations = observations_from_keyframes(rows)
    assert len(observations) == 2
    first = observations[0]
    assert first.kind == "text"
    assert first.subject == "1 SOMA CON"
    assert first.t_ms == 23500
    assert first.provenance.source_channel == "ocr"


def test_keyframe_empty_ocr_yields_nothing() -> None:
    rows = [{"t": 0.0, "frame": "f.jpg", "caption": "x", "ocr": []}]
    assert observations_from_keyframes(rows) == []


def test_entity_text_becomes_observation() -> None:
    rows = [
        {
            "t": 1.0,
            "frame": "f.jpg",
            "parse_ok": True,
            "persons": [],
            "text_objects": [{"object": "laptop screen", "logo_or_text": "WeTransfer"}],
        }
    ]
    observations = observations_from_entity_capture(rows)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.kind == "text"
    assert obs.subject == "WeTransfer"
    assert obs.provenance.source_channel == "entity_text"
    assert obs.attributes[0].name == "object"
    assert obs.attributes[0].value == "laptop screen"


def test_entity_holding_becomes_object_observation() -> None:
    rows = [
        {
            "t": 1.5,
            "frame": "f.jpg",
            "parse_ok": True,
            "persons": [{"holding": ["laptop"], "position": "left"}],
            "text_objects": [],
        }
    ]
    observations = observations_from_entity_capture(rows)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.kind == "object"
    assert obs.subject == "laptop"
    assert obs.provenance.source_channel == "entity_capture"


def test_t_ms_equals_captured_at_ms_invariant() -> None:
    rows = [{"t": 2.0, "frame": "f.jpg", "ocr": ["HELLO"]}]
    obs = observations_from_keyframes(rows)[0]
    assert obs.t_ms == obs.provenance.captured_at_ms == 2000


def test_confidence_from_row_is_used_and_clamped() -> None:
    rows = [{"t": 0.0, "frame": "f.jpg", "ocr": ["A"], "confidence": 1.5}]
    obs = observations_from_keyframes(rows)[0]
    assert obs.confidence.value == 1.0
    rows_default = [{"t": 0.0, "frame": "f.jpg", "ocr": ["B"]}]
    assert observations_from_keyframes(rows_default)[0].confidence.value == 0.5


def test_parse_ok_false_rows_are_skipped() -> None:
    rows = [
        {
            "t": 1.0,
            "parse_ok": False,
            "text_objects": [{"logo_or_text": "junk"}],
            "persons": [],
        }
    ]
    assert observations_from_entity_capture(rows) == []


def test_malformed_rows_are_skipped() -> None:
    rows = [
        "not a dict",  # type: ignore[list-item]
        {"frame": "f.jpg", "ocr": ["NO TIME"]},  # missing t
        {"t": "bad", "ocr": ["BAD T"]},  # non-numeric t
        {"t": -1.0, "ocr": ["NEG"]},  # negative t
        {"t": 0.0, "ocr": ["   "]},  # blank subject
    ]
    assert observations_from_keyframes(rows) == []


def test_load_observations_combines_and_sorts(tmp_path: Path) -> None:
    kf = [{"t": 5.0, "frame": "a.jpg", "ocr": ["LATE"]}]
    entity = [
        {
            "t": 1.0,
            "parse_ok": True,
            "persons": [],
            "text_objects": [{"logo_or_text": "EARLY"}],
        }
    ]
    (tmp_path / "kf_memory.json").write_text(json.dumps(kf), encoding="utf-8")
    (tmp_path / "entity_capture.json").write_text(json.dumps(entity), encoding="utf-8")
    observations = load_observations(str(tmp_path))
    assert [o.subject for o in observations] == ["EARLY", "LATE"]
    assert [o.t_ms for o in observations] == [1000, 5000]


def test_load_observations_tolerates_ndjson_entity(tmp_path: Path) -> None:
    line = json.dumps(
        {
            "t": 0.0,
            "parse_ok": True,
            "persons": [],
            "text_objects": [{"logo_or_text": "NDJSON"}],
        }
    )
    (tmp_path / "entity_capture.json").write_text(line + "\n" + line + "\n", encoding="utf-8")
    observations = load_observations(str(tmp_path))
    assert len(observations) == 2
    assert observations[0].subject == "NDJSON"


def test_load_observations_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_observations(str(tmp_path / "does_not_exist")) == []


def test_load_observations_empty_dir_returns_empty(tmp_path: Path) -> None:
    assert load_observations(str(tmp_path)) == []
