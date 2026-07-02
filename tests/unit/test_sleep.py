from __future__ import annotations

from trace_memory.store import (
    SleepConsolidator,
    TraceMemoryStore,
    audio_origin_anchor,
    observation_time_range,
    session_coordinate_frame,
    world_point_anchor,
)


class StubEmbedder:
    mode = "sentence-transformer"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(1.0, 0.0, 0.0) for _ in texts]


def test_sleep_consolidator_creates_abstractions_and_links(tmp_path) -> None:
    store = TraceMemoryStore(tmp_path / "sleep.sqlite3", embedder=StubEmbedder())
    coordinate_frame = session_coordinate_frame("sleep-fixture")
    try:
        store.write_canonical_observation(
            text="person A is wearing a green shirt",
            t_ms=1000,
            source="fixture.entity",
            helper_type="colour",
            coordinate_frame=coordinate_frame,
            time_range=observation_time_range(1000),
            spatial_anchor=world_point_anchor((0.0, 0.0, 0.0)),
            provenance={"frame_support": [0]},
            source_support={"frame_ids": ["f0"]},
            metadata={"subject_hint": "person A", "attribute_kind": "color", "attribute_value": "green"},
            node_type="observation",
            immutable_raw=True,
        )
        store.write_canonical_observation(
            text='person A transcript: "hello there"',
            t_ms=1100,
            source="fixture.entity",
            helper_type="whisper",
            coordinate_frame=coordinate_frame,
            time_range=observation_time_range(1100),
            spatial_anchor=audio_origin_anchor((0.1, 0.0, 0.0)),
            provenance={"frame_support": [1]},
            source_support={"frame_ids": ["f1"]},
            metadata={"subject_hint": "person A", "transcript": "hello there"},
            node_type="observation",
            immutable_raw=True,
        )
        from trace_memory.store.author import deterministic_author
        summary = SleepConsolidator(store, author=deterministic_author).consolidate()
        abstractions = store.get_abstractions()
        links = [link for link in store.links() if link.link_type == "supports_memory"]
    finally:
        store.close()

    assert summary.abstraction_count == 1
    assert summary.link_count >= 1
    assert abstractions
    assert links
