from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import trace_brain_server as brain  # noqa: E402
from trace_memory.brain.agent import AgentAnswer  # noqa: E402


def test_ask_routes_through_store_agent(tmp_path, monkeypatch) -> None:
    """When the store agent returns a grounded answer, /ask serves it (source=store_agent)
    and the cockpit 'wired' flag is set — proving the greenfield brain is in the live path."""
    monkeypatch.setattr(brain, "STORE_AGENT_ENABLED", True)
    monkeypatch.setattr(brain, "CAPTURES", tmp_path)
    flag = tmp_path / "reasoner_wired.flag"
    monkeypatch.setattr(brain, "_STORE_WIRED_FLAG", flag)

    mdir = tmp_path / "live"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "kf_memory.json").write_text("[]")

    grounded = AgentAnswer(
        answer="A red mug.",
        evidence_chain=({"id": "n1", "text": "a red mug on the desk"},),
        confidence=0.81,
        refused=False,
        retrieval_mode="semantic",
    )
    monkeypatch.setattr(brain, "_store_agent_answer", lambda q, allow_frontier: grounded)

    res = brain._ask_impl({"moment_id": "live", "question": "what mug did I see"})
    assert res["source"] == "store_agent"
    assert res["refused"] is False
    assert "red mug" in res["answer"].lower()
    assert res["citations"] and res["citations"][0]["frame"] == "n1"
    assert flag.exists()
