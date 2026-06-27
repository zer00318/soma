from __future__ import annotations

import json

import scripts.trace_brain_server as brain
from trace_memory.store import TraceMemoryStore


def test_capture_promotes_live_text_field_to_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    brain._LIVE.clear()

    result = brain._capture(
        {
            "moment_id": "live",
            "source": "live_screen",
            "memory_text": "\n".join(
                [
                    "SCENE: street",
                    "OBJECTS: signs",
                    "TEXT: THE BODY SHOP | PANDORA",
                    "PEOPLE: many",
                ]
            ),
        }
    )

    assert result["ok"] is True
    rows = json.loads((tmp_path / "live" / "kf_memory.json").read_text())
    assert rows[0]["ocr"] == ["THE BODY SHOP", "PANDORA"]


def test_ask_passes_latest_anchor_and_keeps_consensus_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    moment = tmp_path / "live"
    moment.mkdir()
    (moment / "kf_memory.json").write_text(
        json.dumps(
            [
                {"t": 2.0, "frame": "f_0", "caption": "", "ocr": ["older"]},
                {"t": 7.5, "frame": "f_1", "caption": "", "ocr": ["THE BODY SHOP"]},
            ]
        )
    )
    seen: dict[str, float | None] = {}

    def fake_ask(question, memory_path, model, anchor=None):
        seen["anchor"] = anchor
        return {"answer": "THE BODY SHOP", "scenes": [], "source": "ocr_consensus", "support": 3}

    monkeypatch.setattr(brain.ask_home, "ask", fake_ask)
    monkeypatch.setattr(brain.ask_home, "_is_refusal", lambda answer: False)

    result = brain._ask({"moment_id": "live", "question": "What text did I read?"})

    assert seen["anchor"] == 7.5
    assert result["answer"] == "THE BODY SHOP"
    assert result["source"] == "ocr_consensus"
    assert result["refused"] is False
    assert result["citations"] == [{"t": 7.5, "frame": None, "label": "7.5s"}]


def test_capture_writes_unified_store_as_phone_camera(tmp_path, monkeypatch) -> None:
    # Live phone captures land in the ONE unified store (founder's model), tagged
    # phone_camera — the live PHYSICAL context that makes this not Windows Recall.
    unified = tmp_path / "trace_store.sqlite3"
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    monkeypatch.setattr(brain, "UNIFIED_STORE_DB", str(unified))
    brain._LIVE.clear()

    brain._capture(
        {
            "moment_id": "live",
            "source": "native_vision",
            "memory_text": "OBJECT | pesto jar | con peperoncino | likely",
            "metadata": {"pose": {"yaw": 1.2, "pitch": 0.4}},
            "location_hint": "kitchen shelf",
        }
    )

    store = TraceMemoryStore(unified)
    try:
        nodes = store.nodes(node_types=("observation",))
    finally:
        store.close()

    assert len(nodes) == 1
    assert "pesto jar" in nodes[0].text.lower()
    assert nodes[0].place == "kitchen shelf"
    assert nodes[0].source == "phone_camera"
