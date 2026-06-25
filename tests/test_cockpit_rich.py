from __future__ import annotations

import json
from pathlib import Path

from scripts import cockpit_ask_server as cockpit
from trace_memory.adapters.sqlite_eventlog import SqliteEventLog
from trace_memory.domain.confidence import Confidence
from trace_memory.domain.observation import Observation
from trace_memory.domain.provenance import Provenance


def _observation(subject: str, t_ms: int, *, spatial_anchor: str) -> Observation:
    return Observation(
        kind="object",
        subject=subject,
        attributes=(),
        t_ms=t_ms,
        spatial_anchor=spatial_anchor,
        confidence=Confidence(0.8),
        provenance=Provenance(
            event_id=f"evt-{subject}-{t_ms}",
            source_channel="fixture",
            captured_at_ms=t_ms,
        ),
    )


def test_status_snapshot_prefers_event_log_counts(tmp_path, monkeypatch) -> None:
    captures_root = tmp_path / "data" / "phone_captures"
    capture_dir = captures_root / "fixture_capture"
    capture_dir.mkdir(parents=True)
    live_dir = captures_root / "live"
    live_dir.mkdir(parents=True)
    (live_dir / "kf_memory.json").write_text("[]", encoding="utf-8")

    log = SqliteEventLog(str(capture_dir / "events.db"))
    log.append(_observation("water bottle", 1000, spatial_anchor="shelf a"))
    log.append(_observation("water bottle", 1100, spatial_anchor="shelf a"))
    log.append(_observation("coffee mug", 1200, spatial_anchor="desk b"))
    log.close()

    monkeypatch.setattr(cockpit, "PHONE_CAPTURES_ROOT", captures_root)
    monkeypatch.setattr(cockpit, "LIVE_MEM", live_dir / "kf_memory.json")
    monkeypatch.setattr(cockpit, "OCR_MEMO", tmp_path / "missing_ocr_memory.json")
    monkeypatch.setattr(cockpit, "ollama_up", lambda: False)
    cockpit._EVENT_CACHE.clear()
    cockpit._LIVE_CACHE.clear()
    cockpit._DEMO_CACHE.clear()

    status = cockpit._status_snapshot()

    assert status["things_remembered"] == 2
    assert status["observation_count"] == 3
    assert status["bound_entity_count"] == 2
    assert status["distinct_subject_count"] == 2


def test_agent_plan_exposes_rich_helpers_and_oracle_panels() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root / "ops" / "cockpit" / "agent_plan.json").read_text(encoding="utf-8"))

    helpers = plan["helpers"]
    assert isinstance(helpers, list)
    assert len(helpers) >= 15
    for helper in helpers:
        assert helper["name"]
        assert helper["role"]
        assert helper["status"] in {"live", "partial", "not-wired", "demoted"}
        assert helper["evidence"]

    critical_path = plan["critical_path"]
    assert len(critical_path) == 7
    assert [item["id"] for item in critical_path] == [f"CP{i}" for i in range(1, 8)]

    honest_number = plan["honest_number"]
    assert honest_number["n"] > 0
    assert "correct_ci_95" in honest_number
    assert "hallucination_ci_95" in honest_number
    assert "FIXTURE" in honest_number["note"]
