from __future__ import annotations

import inspect
import json

import evaluation.annotate_live as al
from trace_memory.store import TraceMemoryStore


def _seed(tmp_path):
    store = TraceMemoryStore(tmp_path / "eval.sqlite3")
    store.write_observation(
        text="entity jar | Nutella | state=empty",
        t_ms=1000,
        source="fixture.entity",
        provenance={},
        node_type="entity",
        metadata={"label": "Nutella"},
    )
    return store


def test_no_rigged_heuristic_in_eval() -> None:
    """The eval must NOT carry its own hardcoded-brand/flavour answer rig — otherwise it
    grades the rig with the rig. It scores the SAME agent the demo uses."""
    src = inspect.getsource(al).lower()
    for needle in ('"pringles"', '"pesto"', "con peperoncino", '"macbook"', "count_re.match"):
        assert needle not in src, f"rigged eval heuristic still present: {needle}"


def test_answer_question_delegates_to_production_agent(tmp_path) -> None:
    """With no LLM backend the production agent REFUSES (honesty floor) — it must never
    fabricate from a pattern match. Proves the eval routes through the real agent."""
    store = _seed(tmp_path)
    try:
        out = al.answer_question(
            store, "how many nutella jars are there", reasoner="heuristic",
            model="x", host="http://127.0.0.1:11434",
        )
    finally:
        store.close()
    assert out["refused"] is True
    assert "evidence_ids" in out


def test_writes_store_eval_with_cockpit_keys(tmp_path) -> None:
    """The eval must emit evaluation/ras/store_eval.json with the EXACT keys the honest
    cockpit reads (answered_pct, halluc_pct, n) so the dashboard number is eval-backed."""
    out = tmp_path / "store_eval.json"
    summary = {"total": 4, "answered": 3, "correct": 3, "confident_wrong": 0}
    payload = al.write_store_eval(summary, path=out)
    on_disk = json.loads(out.read_text())
    for key in ("answered_pct", "halluc_pct", "n"):
        assert key in payload and key in on_disk
    assert on_disk["n"] == 4
