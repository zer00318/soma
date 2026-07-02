from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from trace_memory.brain import TraceMemoryAgent
from trace_memory.store import (
    SleepConsolidator,
    TraceMemoryStore,
    audio_origin_anchor,
    observation_time_range,
    scene_frustum_anchor,
    session_coordinate_frame,
    world_point_anchor,
)

_LIGHT_INGEST_SPEC = importlib.util.spec_from_file_location(
    "light_ingest_mod",
    Path(__file__).resolve().parents[2] / "scripts" / "light_ingest.py",
)
assert _LIGHT_INGEST_SPEC and _LIGHT_INGEST_SPEC.loader
light_ingest_mod = importlib.util.module_from_spec(_LIGHT_INGEST_SPEC)
_LIGHT_INGEST_SPEC.loader.exec_module(light_ingest_mod)

_VALIDATE_FIXTURES_SPEC = importlib.util.spec_from_file_location(
    "validate_world_grounded_fixtures_mod",
    Path(__file__).resolve().parents[2] / "scripts" / "validate_world_grounded_fixtures.py",
)
assert _VALIDATE_FIXTURES_SPEC and _VALIDATE_FIXTURES_SPEC.loader
validate_fixtures_mod = importlib.util.module_from_spec(_VALIDATE_FIXTURES_SPEC)
_VALIDATE_FIXTURES_SPEC.loader.exec_module(validate_fixtures_mod)


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                (
                    1.0 if "green" in lowered else 0.0,
                    1.0 if "hello" in lowered else 0.0,
                    1.0 if "shirt" in lowered else 0.0,
                    1.0 if "person" in lowered else 0.0,
                )
            )
        return vectors


class ConflictEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(0.0, 0.0, 0.0, 0.0) for _ in texts]


def test_canonical_observation_round_trip(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "grounded.sqlite3", embedder=StubEmbedder())
    try:
        node = store.write_canonical_observation(
            text="scene observation",
            t_ms=1000,
            source="fixture.helper",
            helper_type="vlm",
            coordinate_frame=session_coordinate_frame("session-a"),
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((1.0, 2.0, 3.0)),
            provenance={"frame": "0001.jpg"},
            source_support={"frame_ids": ["0001.jpg"]},
            immutable_raw=True,
        )
        fetched = store.read_observation(node.id)
    finally:
        store.close()

    assert fetched is not None
    assert fetched.helper_type == "vlm"
    assert fetched.coordinate_frame is not None
    assert fetched.coordinate_frame.session_id == "session-a"
    assert fetched.spatial_anchor is not None
    assert fetched.spatial_anchor.kind == "world_point"
    assert fetched.source_support["frame_ids"] == ["0001.jpg"]
    assert fetched.immutable_raw is True


def test_sleep_binder_composes_cross_helper_memory(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "binder.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        store.write_canonical_observation(
            text="person A shirt colour is green",
            t_ms=1000,
            source="fixture.colour",
            helper_type="colour",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((0.0, 0.0, 0.0)),
            provenance={"helper": "colour"},
            source_support={"frame_ids": ["f0"]},
            metadata={"subject_hint": "person A", "attribute_kind": "color", "attribute_value": "green"},
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text="person A shirt texture is ribbed",
            t_ms=1200,
            source="fixture.texture",
            helper_type="texture",
            coordinate_frame=frame,
            time_range=observation_time_range(1200),
            spatial_anchor=world_point_anchor((0.1, 0.0, 0.0)),
            provenance={"helper": "texture"},
            source_support={"frame_ids": ["f1"]},
            metadata={"subject_hint": "person A", "attribute_kind": "texture", "attribute_value": "ribbed"},
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text='person A transcript: "hello there"',
            t_ms=1300,
            source="fixture.whisper",
            helper_type="whisper",
            coordinate_frame=frame,
            time_range=observation_time_range(1300),
            spatial_anchor=audio_origin_anchor((0.05, 0.0, 0.0)),
            provenance={"helper": "whisper"},
            source_support={"frame_ids": ["f2"], "audio_spans": [[1200, 1300]]},
            metadata={"subject_hint": "person A", "transcript": "hello there"},
            immutable_raw=True,
        )

        summary = SleepConsolidator(store).consolidate()
        memories = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
        support_links = [link for link in store.links() if link.link_type == "supports_memory"]
    finally:
        store.close()

    assert summary.abstraction_count == 1
    assert summary.composed_memory_count == 1
    assert len(memories) == 1
    assert "green" in memories[0].text.lower()
    assert "hello there" in memories[0].text.lower()
    assert len(support_links) == 3


def test_sleep_binder_keeps_apart_distinct_people(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "separate.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        for person, x in (("person A", 0.0), ("person B", 3.0)):
            store.write_canonical_observation(
                text=f"{person} shirt colour is green",
                t_ms=1000,
                source="fixture.colour",
                helper_type="colour",
                coordinate_frame=frame,
                time_range=observation_time_range(1000),
                spatial_anchor=world_point_anchor((x, 0.0, 0.0)),
                provenance={"helper": "colour"},
                source_support={"frame_ids": [f"{person}-0"]},
                metadata={"subject_hint": person, "attribute_kind": "color", "attribute_value": "green"},
                immutable_raw=True,
            )
            store.write_canonical_observation(
                text=f'{person} transcript: "hello there"',
                t_ms=1100,
                source="fixture.whisper",
                helper_type="whisper",
                coordinate_frame=frame,
                time_range=observation_time_range(1100),
                spatial_anchor=audio_origin_anchor((x + 0.05, 0.0, 0.0)),
                provenance={"helper": "whisper"},
                source_support={"frame_ids": [f"{person}-1"]},
                metadata={"subject_hint": person, "transcript": "hello there"},
                immutable_raw=True,
            )

        SleepConsolidator(store).consolidate()
        memories = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
    finally:
        store.close()

    assert len(memories) == 2
    assert memories[0].metadata["subject_hint"] != memories[1].metadata["subject_hint"]


def test_sleep_binder_bounds_scene_memory_to_local_view(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "scene-bounds.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    created: dict[str, str] = {}
    try:
        for name, t_ms, yaw_deg, text in (
            ("nutella-0", 0, -30.0, "two Nutella jars on the white bedside table"),
            ("nutella-1", 1000, -15.0, "three Nutella jars beside the charger on the bedside table"),
            ("nutella-2", 2000, 0.0, "Nutella jars with pesto jar on the nightstand"),
            ("fan-0", 3000, 30.0, "black laptop and desk fan on the windowsill"),
            ("fan-1", 4000, 45.0, "open laptop beside the black fan on the ledge"),
        ):
            node = store.write_canonical_observation(
                text=text,
                t_ms=t_ms,
                source="fixture.vlm",
                helper_type="vlm_object",
                coordinate_frame=frame,
                time_range=observation_time_range(t_ms),
                spatial_anchor=scene_frustum_anchor(
                    pose={"yaw_deg": yaw_deg, "pitch_deg": 75.0, "roll_deg": 0.0}
                ),
                provenance={"helper": "vlm"},
                source_support={"frame_ids": [name]},
                metadata={"subject_hint": "nutella jar" if "nutella" in text.lower() else "desk fan"},
                immutable_raw=True,
            )
            created[name] = node.id

        SleepConsolidator(store).consolidate()
        memories = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
    finally:
        store.close()

    assert len(memories) >= 2
    support_sets = [set(memory.metadata["support_ids"]) for memory in memories]
    assert any(
        {
            created["nutella-0"],
            created["nutella-1"],
            created["nutella-2"],
        }.issubset(support_ids)
        for support_ids in support_sets
    )
    assert any({created["fan-0"], created["fan-1"]}.issubset(support_ids) for support_ids in support_sets)
    assert all(
        not ({created["nutella-0"], created["fan-1"]}.issubset(support_ids))
        for support_ids in support_sets
    )


def test_sleep_binder_skips_generic_scene_vlm_memory(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "scene-generic.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        for t_ms, yaw_deg, text in (
            (0, -30.0, "Large Nutella jar and white charger on bedside table."),
            (1000, -20.0, "Large Nutella jar and white charger on bedside table."),
            (2000, -10.0, "Large Nutella jar and white charger on bedside table."),
        ):
            store.write_canonical_observation(
                text=text,
                t_ms=t_ms,
                source="fixture.vlm",
                helper_type="vlm",
                coordinate_frame=frame,
                time_range=observation_time_range(t_ms),
                spatial_anchor=scene_frustum_anchor(
                    pose={"yaw_deg": yaw_deg, "pitch_deg": 75.0, "roll_deg": 0.0}
                ),
                provenance={"helper": "vlm"},
                source_support={"frame_ids": [f"f-{t_ms}"]},
                immutable_raw=True,
            )
        summary = SleepConsolidator(store).consolidate()
        memories = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
    finally:
        store.close()

    assert summary.composed_memory_count == 0
    assert memories == ()


def test_sleep_binder_skips_mixed_subject_scene_cluster(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "scene-mixed.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        for index, (text, subject_hint, yaw_deg) in enumerate(
            (
                ("Nutella jar on the white bedside table", "nutella jar", -20.0),
                ("White power adapter beside the jar", "power adapter", -18.0),
                ("Black cables near the adapter", "cables", -16.0),
                ("Snack bag on the same table", "snack bag", -14.0),
            )
        ):
            store.write_canonical_observation(
                text=text,
                t_ms=index * 500,
                source="fixture.vlm",
                helper_type="vlm_object",
                coordinate_frame=frame,
                time_range=observation_time_range(index * 500),
                spatial_anchor=scene_frustum_anchor(
                    pose={"yaw_deg": yaw_deg, "pitch_deg": 75.0, "roll_deg": 0.0}
                ),
                provenance={"helper": "vlm"},
                source_support={"frame_ids": [f"f-{index}"]},
                metadata={"subject_hint": subject_hint},
                immutable_raw=True,
            )
        summary = SleepConsolidator(store).consolidate()
        memories = store.nodes(node_types=("entity_memory", "event_memory", "group_memory"))
    finally:
        store.close()

    assert summary.composed_memory_count == 0
    assert memories == ()


def test_light_ingest_extracts_object_and_text_atoms() -> None:
    text = """
## Physical Objects

1. **Eyeglasses** – black frame, folded, resting on white surface beneath tray
2. **Water bottle** – white, cylindrical, cork lid, upright

## Transcribed Text (Verbatim)

`Claude File Edit View Window Help`
`Sun 26 Jan 16:18`
""".strip()

    atoms = light_ingest_mod._extract_frame_atoms(text)

    assert [atom["helper_type"] for atom in atoms] == ["vlm_object", "vlm_object", "ocr", "ocr"]
    assert atoms[0]["subject_hint"] == "Eyeglasses"
    assert "white surface beneath tray" in atoms[0]["text"].lower()
    assert atoms[2]["section_kind"] == "screen_text"
    assert atoms[2]["text"] == "Claude File Edit View Window Help"


def test_light_ingest_extracts_relation_helper_atoms() -> None:
    text = """
- Blanket draped over the open suitcase and touching the bed
- 3 pillows visible on the bed
- Eyeglasses under the laptop stand on grey bedsheet
""".strip()

    atoms = light_ingest_mod._extract_helper_atoms(
        text,
        default_kind="relation",
        default_helper_type="spatial_relation",
        default_title="spatial_relations",
    )

    assert [atom["helper_type"] for atom in atoms] == ["spatial_relation", "spatial_relation", "spatial_relation"]
    assert atoms[0]["section_kind"] == "relation"
    assert atoms[0]["subject_hint"] == "Blanket draped over the open suitcase and touching the bed"
    assert "3 pillows visible" in atoms[1]["text"]


def test_light_ingest_treats_screen_state_header_as_screen_text() -> None:
    text = """
## Screen State

- Battery Percentage: 100%
- App visible: Claude
""".strip()

    atoms = light_ingest_mod._extract_helper_atoms(
        text,
        default_kind="screen_text",
        default_helper_type="screen_state",
        default_title="screen_state",
    )

    assert [atom["helper_type"] for atom in atoms] == ["screen_state", "screen_state"]
    assert all(atom["section_kind"] == "screen_text" for atom in atoms)


def test_light_ingest_filters_screen_noise_from_relation_atoms() -> None:
    text = """
- Blanket draped over the open suitcase and touching the bed
- App window titled "Judge vision memory discrepancy" is visible
- File named "trace_capture_20231005_063708_vision_traces.json" is open
""".strip()

    atoms = light_ingest_mod._extract_helper_atoms(
        text,
        default_kind="relation",
        default_helper_type="spatial_relation",
        default_title="spatial_relations",
    )

    assert [atom["text"] for atom in atoms] == [
        "Blanket draped over the open suitcase and touching the bed"
    ]


def test_light_ingest_canonicalizes_relation_helper_parent_text() -> None:
    atoms = [
        {"text": "Blanket draped over the open suitcase and touching the bed"},
        {"text": "3 pillows visible on the bed"},
    ]

    text = light_ingest_mod._canonicalize_helper_text(
        "spatial_relations",
        atoms,
        "raw helper text",
    )

    assert text == "## Spatial Relations\n- Blanket draped over the open suitcase and touching the bed\n- 3 pillows visible on the bed"


def test_agent_prefers_authored_memory_with_citations(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "agent-grounded.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        store.write_canonical_observation(
            text="person A shirt colour is green",
            t_ms=1000,
            source="fixture.colour",
            helper_type="colour",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((0.0, 0.0, 0.0)),
            provenance={"helper": "colour"},
            source_support={"frame_ids": ["f0"]},
            metadata={"subject_hint": "person A", "attribute_kind": "color", "attribute_value": "green"},
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text='person A transcript: "hello there"',
            t_ms=1100,
            source="fixture.whisper",
            helper_type="whisper",
            coordinate_frame=frame,
            time_range=observation_time_range(1100),
            spatial_anchor=audio_origin_anchor((0.05, 0.0, 0.0)),
            provenance={"helper": "whisper"},
            source_support={"frame_ids": ["f1"]},
            metadata={"subject_hint": "person A", "transcript": "hello there"},
            immutable_raw=True,
        )
        SleepConsolidator(store).consolidate()
        answer = TraceMemoryAgent(store, reasoner="heuristic").answer(
            "What did the person with the green shirt say?"
        )
    finally:
        store.close()

    assert answer.evidence_chain
    assert answer.evidence_chain[0]["type"] in {"entity_memory", "event_memory", "group_memory"}
    assert answer.evidence_chain[0]["citation_ids"]


def test_agent_pulls_relevant_citation_support_for_speech_question(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "agent-citation-rank.sqlite3", embedder=StubEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        store.write_canonical_observation(
            text="person A shirt colour is green",
            t_ms=1000,
            source="fixture.colour",
            helper_type="colour",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((0.0, 0.0, 0.0)),
            provenance={"helper": "colour"},
            source_support={"frame_ids": ["f0"]},
            metadata={"subject_hint": "person A", "attribute_kind": "color", "attribute_value": "green"},
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text="person A shirt texture is ribbed",
            t_ms=1100,
            source="fixture.texture",
            helper_type="texture",
            coordinate_frame=frame,
            time_range=observation_time_range(1100),
            spatial_anchor=world_point_anchor((0.02, 0.0, 0.0)),
            provenance={"helper": "texture"},
            source_support={"frame_ids": ["f1"]},
            metadata={"subject_hint": "person A", "attribute_kind": "texture", "attribute_value": "ribbed"},
            immutable_raw=True,
        )
        transcript = store.write_canonical_observation(
            text='person A transcript: "hello there"',
            t_ms=1200,
            source="fixture.whisper",
            helper_type="whisper",
            coordinate_frame=frame,
            time_range=observation_time_range(1200),
            spatial_anchor=audio_origin_anchor((0.05, 0.0, 0.0)),
            provenance={"helper": "whisper"},
            source_support={"frame_ids": ["f2"], "audio_spans": [[1100, 1200]]},
            metadata={"subject_hint": "person A", "transcript": "hello there"},
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text='person B transcript: "see you soon"',
            t_ms=1300,
            source="fixture.whisper",
            helper_type="whisper",
            coordinate_frame=frame,
            time_range=observation_time_range(1300),
            spatial_anchor=audio_origin_anchor((3.0, 0.0, 0.0)),
            provenance={"helper": "whisper"},
            source_support={"frame_ids": ["f3"], "audio_spans": [[1200, 1300]]},
            metadata={"subject_hint": "person B", "transcript": "see you soon"},
            immutable_raw=True,
        )

        SleepConsolidator(store).consolidate()
        answer = TraceMemoryAgent(store, reasoner="heuristic").answer(
            "What did the person with the green shirt say?"
        )
    finally:
        store.close()

    assert answer.evidence_chain
    support_ids = [row["id"] for row in answer.evidence_chain[1:4]]
    assert transcript.id in support_ids


def test_agent_prefers_specific_location_evidence_over_conflicting_generic_memory(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "agent-location-rank.sqlite3", embedder=ConflictEmbedder())
    frame = session_coordinate_frame("bedroom-fixture")
    try:
        suitcase = store.write_canonical_observation(
            text="Grey blanket draped over the blue suitcase on the bed.",
            t_ms=1000,
            source="fixture.vlm",
            helper_type="vlm",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=scene_frustum_anchor(
                pose={"yaw_deg": 0.0, "pitch_deg": 75.0, "roll_deg": 0.0}
            ),
            provenance={"helper": "vlm"},
            source_support={"frame_ids": ["f0"]},
            immutable_raw=True,
        )
        bed_only = store.write_canonical_observation(
            text="Grey blanket on the bed surface near the pillows.",
            t_ms=2000,
            source="fixture.vlm",
            helper_type="vlm",
            coordinate_frame=frame,
            time_range=observation_time_range(2000),
            spatial_anchor=scene_frustum_anchor(
                pose={"yaw_deg": 8.0, "pitch_deg": 75.0, "roll_deg": 0.0}
            ),
            provenance={"helper": "vlm"},
            source_support={"frame_ids": ["f1"]},
            immutable_raw=True,
        )
        store.write_observation(
            text="memory with grey and blue",
            t_ms=1000,
            source="sleep.consolidator",
            helper_type="sleep_binder",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=scene_frustum_anchor(
                pose={"yaw_deg": 0.0, "pitch_deg": 75.0, "roll_deg": 0.0}
            ),
            provenance={"builder": "sleep", "support_ids": [suitcase.id]},
            source_support={"support_ids": [suitcase.id]},
            metadata={"support_ids": [suitcase.id], "memory_kind": "entity_memory"},
            node_type="entity_memory",
            derived=True,
            immutable_raw=False,
            node_id="mem-blanket-suitcase",
        )
        store.write_observation(
            text="memory with grey",
            t_ms=2000,
            source="sleep.consolidator",
            helper_type="sleep_binder",
            coordinate_frame=frame,
            time_range=observation_time_range(2000),
            spatial_anchor=scene_frustum_anchor(
                pose={"yaw_deg": 8.0, "pitch_deg": 75.0, "roll_deg": 0.0}
            ),
            provenance={"builder": "sleep", "support_ids": [bed_only.id]},
            source_support={"support_ids": [bed_only.id]},
            metadata={"support_ids": [bed_only.id], "memory_kind": "entity_memory"},
            node_type="entity_memory",
            derived=True,
            immutable_raw=False,
            node_id="mem-blanket-bed",
        )

        answer = TraceMemoryAgent(store, reasoner="heuristic").answer(
            "Where is the blanket currently?"
        )
    finally:
        store.close()

    assert answer.evidence_chain
    evidence_ids = [row["id"] for row in answer.evidence_chain[:4]]
    assert suitcase.id in evidence_ids
    assert evidence_ids.index(suitcase.id) < evidence_ids.index(bed_only.id)


def test_export_world_store_can_export_raw_helper_observations_only(tmp_path) -> None:
    store_path = tmp_path / "helper-store.sqlite3"
    export_path = tmp_path / "helper_outputs.json"
    store = TraceMemoryStore(store_path, embedder=StubEmbedder())
    frame = session_coordinate_frame("fixture-session")
    try:
        obs = store.write_canonical_observation(
            text="person A shirt colour is green",
            t_ms=1000,
            source="fixture.colour",
            helper_type="colour",
            coordinate_frame=frame,
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((0.0, 0.0, 0.0)),
            provenance={"helper": "colour"},
            source_support={"frame_ids": ["f0"]},
            immutable_raw=True,
        )
        store.write_observation(
            text="person A with green; person A saying hello there",
            t_ms=1100,
            source="sleep.consolidator",
            helper_type="sleep_binder",
            coordinate_frame=frame,
            time_range=observation_time_range(1100),
            spatial_anchor=scene_frustum_anchor(
                pose={"yaw_deg": 0.0, "pitch_deg": 75.0, "roll_deg": 0.0}
            ),
            provenance={"builder": "sleep", "support_ids": [obs.id]},
            source_support={"support_ids": [obs.id]},
            metadata={"support_ids": [obs.id], "memory_kind": "event_memory"},
            node_type="event_memory",
            derived=True,
            immutable_raw=False,
        )
    finally:
        store.close()

    subprocess.run(
        [
            sys.executable,
            "scripts/export_world_store.py",
            "--store",
            str(store_path),
            "--out",
            str(export_path),
            "--node-types",
            "observation",
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        check=True,
    )

    rows = json.loads(export_path.read_text())
    assert len(rows) == 1
    assert rows[0]["node_type"] == "observation"
    assert rows[0]["immutable_raw"] is True
    assert rows[0]["derived"] is False


def test_helper_fixture_validator_rejects_authored_memory_pollution(tmp_path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "helper_outputs.json").write_text(
        json.dumps(
            [
                {
                    "id": "obs-1",
                    "node_type": "observation",
                    "text": "raw helper observation",
                    "helper_type": "vlm",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 0.0}},
                    "time_range": {"start_ms": 0, "end_ms": 0},
                    "derived": False,
                    "immutable_raw": True,
                },
                {
                    "id": "mem-1",
                    "node_type": "event_memory",
                    "text": "authored memory",
                    "helper_type": "sleep_binder",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 0.0}},
                    "time_range": {"start_ms": 0, "end_ms": 0},
                    "derived": True,
                    "immutable_raw": False,
                },
            ],
            indent=2,
        )
    )

    with pytest.raises(SystemExit, match="raw observations only"):
        validate_fixtures_mod.validate_helper(root)


def test_helper_fixture_validator_requires_multiple_helper_types(tmp_path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "helper_outputs.json").write_text(
        json.dumps(
            [
                {
                    "id": "obs-1",
                    "node_type": "observation",
                    "text": "scene one",
                    "helper_type": "vlm",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 0.0}},
                    "time_range": {"start_ms": 0, "end_ms": 0},
                    "derived": False,
                    "immutable_raw": True,
                },
                {
                    "id": "obs-2",
                    "node_type": "observation",
                    "text": "scene two",
                    "helper_type": "vlm",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 10.0}},
                    "time_range": {"start_ms": 1000, "end_ms": 1000},
                    "derived": False,
                    "immutable_raw": True,
                },
            ],
            indent=2,
        )
    )

    with pytest.raises(SystemExit, match="multiple helper types"):
        validate_fixtures_mod.validate_helper(root)


def test_helper_fixture_validator_rejects_relation_screen_noise(tmp_path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "helper_outputs.json").write_text(
        json.dumps(
            [
                {
                    "id": "obs-1",
                    "node_type": "observation",
                    "text": "Blanket draped over the open suitcase",
                    "helper_type": "spatial_relation",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 0.0}},
                    "time_range": {"start_ms": 0, "end_ms": 0},
                    "derived": False,
                    "immutable_raw": True,
                },
                {
                    "id": "obs-3",
                    "node_type": "observation",
                    "text": "App window titled \"Judge vision memory discrepancy\" is visible",
                    "helper_type": "relation_helper",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 10.0}},
                    "time_range": {"start_ms": 1000, "end_ms": 1000},
                    "derived": False,
                    "immutable_raw": True,
                },
                {
                    "id": "obs-4",
                    "node_type": "observation",
                    "text": "Battery Percentage: 48%",
                    "helper_type": "screen_state",
                    "coordinate_frame": {"session_id": "s", "origin_id": "o"},
                    "spatial_anchor": {"kind": "scene_frustum", "orientation": {"yaw_deg": 10.0}},
                    "time_range": {"start_ms": 1000, "end_ms": 1000},
                    "derived": False,
                    "immutable_raw": True,
                },
            ],
            indent=2,
        )
    )

    with pytest.raises(SystemExit, match="screen-state noise"):
        validate_fixtures_mod.validate_helper(root)


def test_brain_fixture_validator_accepts_supported_heuristic_evidence_chain(tmp_path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "brain_outputs.json").write_text(
        json.dumps(
            [
                {
                    "question": "What did the person with the green shirt say?",
                    "answer": "I don't know",
                    "refused": True,
                    "confidence": 0.15,
                    "reasoner": "heuristic",
                    "expect_subject": "person A",
                    "expect_words": ["hello", "there"],
                    "evidence_chain": [
                        {
                            "id": "mem-1",
                            "type": "event_memory",
                            "text": 'person A with green and ribbed; person A saying "hello there"',
                            "citation_ids": ["obs-1", "obs-2"],
                        },
                        {
                            "id": "obs-1",
                            "type": "observation",
                            "text": "person A shirt colour is green",
                            "citation_ids": [],
                        },
                        {
                            "id": "obs-2",
                            "type": "observation",
                            "text": 'person A transcript: "hello there"',
                            "citation_ids": [],
                        },
                    ],
                }
            ],
            indent=2,
        )
    )

    validate_fixtures_mod.validate_brain(root)
