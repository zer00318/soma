"""Precise, graph-aware retrieval — Layer 1 tool for the agentic brain.

The founder's store principle: hand the brain *the right few notes, not the nearest 500*
(minimal sufficient slice, not the biggest pile — the anti-bloat fix). Plain ``store.search``
returns a flat top-k ranked over every node; this assembles a small slice by:
  1. SEED — hybrid embed+lexical top-k over ALL node types (raw observations INCLUDED, not
     composed-memory-first — raw observations frequently hold the literal answer).
  2. EXPAND — pull link-neighbours (succession / co-occurrence / entity-support) of the
     strongest seeds, so the brain sees the local context, not isolated rows.
  3. TRIM — keep only ``max_nodes`` (minimal sufficient), each tagged with why it's here
     and its provenance, so the brain can show its work and refuse at the edge.

It is a TOOL the brain calls; it does not reason or decide relevance semantics itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from trace_memory.store.models import MemoryNode

# default edges worth expanding across — open list, the caller may override.
_DEFAULT_EXPAND_LINKS = (
    "succession",
    "candidate_same_context",
    "candidate_same_memory",
    "supports_memory",
    "supersedes",
)


@dataclass(frozen=True)
class RetrievedNode:
    node: MemoryNode
    score: float
    reason: str  # "seed" or "expand:<link_type>"


@dataclass(frozen=True)
class PreciseSlice:
    query: str
    nodes: tuple[RetrievedNode, ...]
    retrieval_mode: str

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.node.id for item in self.nodes)

    def render(self) -> str:
        """Provenance-tagged text the brain reads — minimal slice, each line traceable."""
        lines: list[str] = []
        for item in self.nodes:
            node = item.node
            prov = node.source_support or node.provenance or {}
            frame = ""
            for key in ("frame", "frame_ids", "frame_paths"):
                if key in prov:
                    frame = f" frame={prov[key]}"
                    break
            lines.append(
                f"[{node.node_type}/{node.source}{frame} via {item.reason} "
                f"score={item.score:.3f}]\n{node.text.strip()}"
            )
        return "\n\n".join(lines)


def precise_retrieve(
    store: Any,
    query: str,
    *,
    seed_k: int = 8,
    max_nodes: int = 8,
    expand_from: int = 4,
    neighbor_limit: int = 6,
    expand_decay: float = 0.5,
    min_seed_score: float = 0.0,
    sources: Iterable[str] | None = None,
    node_types: Iterable[str] | None = None,
    expand_link_types: Iterable[str] | None = _DEFAULT_EXPAND_LINKS,
) -> PreciseSlice:
    """Return a minimal sufficient, provenance-tagged slice for ``query``.

    ``seed_k``/``max_nodes`` bound the work and the slice (anti-bloat). Only seeds scoring
    strictly above ``min_seed_score`` are kept — ``store.search`` returns ``k`` rows even at
    zero relevance, which is the opposite of precise; an irrelevant node may still enter the
    slice, but only if a relevant seed *links* to it. ``expand_from`` seeds are expanded one
    hop along ``expand_link_types`` so local context rides along.
    """
    seed = store.search(query, k=seed_k, sources=sources, node_types=node_types)
    relevant = [hit for hit in seed.hits if float(hit.score) > min_seed_score]
    chosen: dict[str, RetrievedNode] = {}
    for hit in relevant:
        chosen[hit.node.id] = RetrievedNode(node=hit.node, score=float(hit.score), reason="seed")

    link_types = tuple(expand_link_types) if expand_link_types is not None else None
    for hit in relevant[: max(0, expand_from)]:
        for neighbor in store.neighbors(hit.node.id, link_types=link_types, limit=neighbor_limit):
            existing = chosen.get(neighbor.node.id)
            decayed = float(hit.score) * expand_decay * float(neighbor.edge.weight or 1.0)
            if existing is not None:
                # a node reachable as both seed and neighbour keeps its strongest score
                if decayed > existing.score and existing.reason.startswith("expand"):
                    chosen[neighbor.node.id] = RetrievedNode(
                        node=neighbor.node, score=decayed, reason=f"expand:{neighbor.edge.link_type}"
                    )
                continue
            chosen[neighbor.node.id] = RetrievedNode(
                node=neighbor.node, score=decayed, reason=f"expand:{neighbor.edge.link_type}"
            )

    ranked = sorted(chosen.values(), key=lambda item: (-item.score, item.node.t_ms, item.node.id))
    return PreciseSlice(
        query=query,
        nodes=tuple(ranked[: max(max_nodes, 0)]),
        retrieval_mode=getattr(store, "retrieval_mode", "semantic"),
    )
