from __future__ import annotations

import inspect

import trace_memory.brain.agent as agent_mod
from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import TraceMemoryStore


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                (
                    1.0 if "nutella" in lowered else 0.0,
                    1.0 if "jar" in lowered else 0.0,
                    1.0 if "green" in lowered else 0.0,
                )
            )
        return vectors


def _seed_store(tmp_path):
    store = TraceMemoryStore(tmp_path / "agent.sqlite3", embedder=StubEmbedder())
    store.write_observation(
        text="entity jar | Nutella | state=empty",
        t_ms=1000,
        source="fixture.entity",
        provenance={"frame_support": [0]},
        node_type="entity",
        metadata={"label": "Nutella"},
    )
    return store


def test_retrieval_grounds_the_answer(tmp_path) -> None:
    """The reasoner must RETRIEVE a precise evidence slice for a relevant question —
    grounding is non-negotiable, regardless of whether an LLM backend is present."""
    store = _seed_store(tmp_path)
    try:
        answer = TraceMemoryAgent(store, reasoner="heuristic").answer(
            "How many nutella jars are there?"
        )
    finally:
        store.close()
    assert answer.evidence_chain, "no evidence retrieved — precise retrieval is broken"
    assert any("nutella" in row["text"].lower() for row in answer.evidence_chain)


def test_no_llm_refuses_honestly_never_fabricates(tmp_path) -> None:
    """With NO LLM backend, the agent must REFUSE — never fabricate from a brittle
    regex / hardcoded-brand fast-path. This is the honesty floor (<10% confident-wrong):
    an answer is earned by an evidence-grounded reasoner, not a pattern match."""
    store = _seed_store(tmp_path)
    try:
        agent = TraceMemoryAgent(store, reasoner="heuristic")
        for question in (
            "How many nutella jars are there?",
            "What colour are the gemstones on the rings?",
            "What brand is the jar?",
        ):
            answer = agent.answer(question)
            assert answer.refused is True, (
                f"fabricated an answer for {question!r} with no grounded reasoner"
            )
    finally:
        store.close()


def test_no_regex_fastpath_or_hardcoded_brands() -> None:
    """The rejected schematization must be gone: no COUNT/EXISTS/ATTRIBUTE regex routing
    and no hardcoded brand/colour lists short-circuiting the grounded reasoner."""
    src = inspect.getsource(agent_mod)
    for needle in ('"pringles"', '"pesto"', "COUNT_RE.match", "ATTRIBUTE_RE.match", "EXISTS_RE.match"):
        assert needle not in src, f"rejected schematization still present: {needle}"
