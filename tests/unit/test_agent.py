from __future__ import annotations

import inspect
from types import SimpleNamespace

import trace_memory.brain.agent as agent_mod
from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import (
    TraceMemoryStore,
    observation_time_range,
    scene_frustum_anchor,
    session_coordinate_frame,
)


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


def _write_grounded_observation(
    store: TraceMemoryStore,
    *,
    text: str,
    t_ms: int,
    helper_type: str,
    section_kind: str | None = None,
    helper_prompt: str | None = None,
) -> str:
    node = store.write_canonical_observation(
        text=text,
        t_ms=t_ms,
        source="phone_camera",
        helper_type=helper_type,
        coordinate_frame=session_coordinate_frame("fixture-room"),
        time_range=observation_time_range(t_ms),
        spatial_anchor=scene_frustum_anchor(
            pose={"yaw_deg": 0.0, "pitch_deg": 0.0, "roll_deg": 0.0}
        ),
        provenance={"fixture": True},
        source_support={"frame_ids": [f"f-{t_ms}"]},
        metadata={
            "section_kind": section_kind,
            "helper_prompt": helper_prompt,
        },
        immutable_raw=True,
    )
    return node.id


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


def test_question_hints_are_structural_intents_only() -> None:
    """M3/I5: hints are intent categories mapping to helper types — the drink/mode/app/battery
    content lexicons are deleted. Content questions rank via lexical/embedding overlap."""
    assert "speech" in agent_mod._question_hints("What did she say about the invoice?")
    assert "count" in agent_mod._question_hints("How many jars are there?")
    assert "location" in agent_mod._question_hints("Where is the ladder?")
    hints = agent_mod._question_hints("How can I drink water?")
    assert "drink" not in hints  # no content-lexicon hints survive
    assert "opened" not in agent_mod._tokens("What app was opened on the laptop?")


def test_support_relevance_prefers_positive_drink_evidence() -> None:
    question = "How can I drink water?"
    positive = SimpleNamespace(
        text="White water bottle (cork lid) — next to silver bottle, upright",
        metadata={"section_kind": "relation"},
        helper_type="spatial_relation",
        provenance={},
        source_support={},
    )
    negative = SimpleNamespace(
        text="No drinkable containers visible",
        metadata={"section_kind": "relation"},
        helper_type="spatial_relation",
        provenance={},
        source_support={},
    )

    assert agent_mod._support_relevance(question, positive)[0] > agent_mod._support_relevance(question, negative)[0]


def test_calibration_caps_ambiguous_answer_confidence() -> None:
    confidence = agent_mod._calibrated_confidence(
        "What is the pink cloth near the fan?",
        "A pink/magenta garment or cloth on the ledge.",
        False,
        0.95,
        [
            {
                "text": "Pink/red garment (shirt or towel) lying on ledge to the right of fan",
            }
        ],
    )

    assert confidence < 0.75


def test_calibration_caps_conflicting_current_location_confidence() -> None:
    confidence = agent_mod._calibrated_confidence(
        "Where is the blanket currently?",
        "On the bed, partially draped over the edge.",
        False,
        0.9,
        [
            {"text": "Grey blanket/throw is on top of suitcase (not on bed)"},
            {"text": "Gray blanket/cover is on bed surface, under white pad"},
        ],
    )

    assert confidence < 0.75


def test_calibration_caps_incomplete_count_confidence() -> None:
    confidence = agent_mod._calibrated_confidence(
        "How many nutella jars were there in total?",
        "3 Nutella jars total were visible.",
        False,
        0.9,
        [
            {"text": "3 jars visible in the frame"},
            {"text": "Nutella jar partially visible behind chargers"},
        ],
    )

    assert confidence < 0.75


def test_search_context_surfaces_app_specific_screen_state(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "app.sqlite3", embedder=StubEmbedder())
    try:
        app_id = _write_grounded_observation(
            store,
            text="App: Claude (Anthropic) — Code mode",
            t_ms=1000,
            helper_type="screen_state",
            section_kind="screen_text",
            helper_prompt="screen_state",
        )
        generic_id = _write_grounded_observation(
            store,
            text="Laptop is open, screen ON",
            t_ms=900,
            helper_type="spatial_relation",
            section_kind="relation",
            helper_prompt="spatial_relations",
        )

        search = agent_mod._search_context(
            store,
            "What app was opened on the laptop?",
            max_hops=1,
            sources=("phone_camera",),
        )
        rows = TraceMemoryAgent(
            store,
            reasoner="heuristic",
            restrict_sources=("phone_camera",),
        )._evidence_chain(search, question="What app was opened on the laptop?")
    finally:
        store.close()

    row_ids = [row["id"] for row in rows[:4]]
    assert app_id in row_ids
    assert row_ids.index(app_id) < row_ids.index(generic_id)


def test_search_context_screen_text_sinks_on_physical_questions(tmp_path) -> None:
    """M3/I5 structural rule replacing the old mode-lexicon rescue: screen-text rows are
    demoted on physical-world questions and surface on screen questions."""
    store = TraceMemoryStore(tmp_path / "screen-rank.sqlite3", embedder=StubEmbedder())
    try:
        room_id = _write_grounded_observation(
            store,
            text="Fan on the dresser, blades spinning",
            t_ms=1000,
            helper_type="spatial_relation",
            section_kind="relation",
            helper_prompt="spatial_relations",
        )
        screen_id = _write_grounded_observation(
            store,
            text="Fan speed settings panel with sliders",
            t_ms=1000,
            helper_type="ocr",
            section_kind="screen_text",
            helper_prompt="scene_perception",
        )

        physical = agent_mod._search_context(
            store, "Where is the fan?", max_hops=1, sources=("phone_camera",)
        )
        ranked = [hit.node.id for hit in physical.hits]
        assert room_id in ranked
        if screen_id in ranked:
            assert ranked.index(room_id) < ranked.index(screen_id)

        on_screen = agent_mod._search_context(
            store, "What was on the screen about the fan?", max_hops=1, sources=("phone_camera",)
        )
        assert screen_id in [hit.node.id for hit in on_screen.hits]
    finally:
        store.close()


def test_search_context_surfaces_flavour_reading_without_subject_overlap(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "label.sqlite3", embedder=StubEmbedder())
    try:
        label_id = _write_grounded_observation(
            store,
            text='"PEPERONCINO" (partially visible on pesto label)',
            t_ms=1000,
            helper_type="ocr",
            section_kind="screen_text",
            helper_prompt="scene_perception",
        )
        _write_grounded_observation(
            store,
            text="Barilla (on pesto jar)",
            t_ms=1000,
            helper_type="ocr",
            section_kind="screen_text",
            helper_prompt="scene_perception",
        )

        search = agent_mod._search_context(
            store,
            "What is the flavour of the Barilla pesto?",
            max_hops=1,
            sources=("phone_camera",),
        )
    finally:
        store.close()

    assert label_id in [hit.node.id for hit in search.hits[:4]]
