from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from trace_memory.store import TraceMemoryStore


@dataclass(frozen=True)
class SleepRunSummary:
    grouped_observation_count: int
    abstraction_count: int
    link_count: int
    retrieval_mode: str


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


class SleepConsolidator:
    """Conservative first-pass consolidator.

    It never edits observed rows. It only adds same-entity links for high-confidence
    exact repeats and writes flagged abstractions as derived records.
    """

    def __init__(self, store: TraceMemoryStore) -> None:
        self._store = store

    def consolidate(self) -> SleepRunSummary:
        groups: defaultdict[tuple[str | None, str], list[str]] = defaultdict(list)
        created_links = 0
        created_abstractions = 0

        for node in self._store.nodes(node_types=("entity", "observation")):
            groups[(node.place, _normalize(node.text))].append(node.id)

        for (place, normalized_text), node_ids in groups.items():
            if len(node_ids) < 2:
                continue
            anchor_id = node_ids[0]
            anchor = self._store.read_observation(anchor_id)
            if anchor is None:
                continue
            for node_id in node_ids[1:]:
                self._store.link(
                    anchor_id,
                    node_id,
                    "same_entity",
                    metadata={"builder": "sleep", "basis": "exact_text_place_repeat"},
                )
                created_links += 1
            abstraction_text = (
                f"derived abstraction: repeated memory cluster '{normalized_text}' "
                f"appeared {len(node_ids)} times"
            )
            self._store.write_observation(
                text=abstraction_text,
                t_ms=anchor.t_ms,
                source="sleep.consolidator",
                place=place,
                provenance={"builder": "sleep", "member_ids": node_ids},
                metadata={"cluster_size": len(node_ids), "member_ids": node_ids},
                node_type="abstraction",
                derived=True,
            )
            created_abstractions += 1

        return SleepRunSummary(
            grouped_observation_count=sum(1 for ids in groups.values() if len(ids) > 1),
            abstraction_count=created_abstractions,
            link_count=created_links,
            retrieval_mode=self._store.retrieval_mode,
        )
