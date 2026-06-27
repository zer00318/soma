#!/usr/bin/env python3
"""Bridge between the instance pipeline and the brain server.

The instance pipeline (instance_perceive + instance_graph) runs on the Mac and
produces a scene graph from a single high-res frame. This module provides the
three functions the brain server calls:

  perceive_and_graph(frame_path, moment, graphs_store) -> dict
      Run detector + per-crop VLM + build scene graph; store in graphs_store.

  answer_from_graph(question, moment, graphs_store, ollama_host, model) -> dict | None
      Answer a question from a stored graph, or None if no graph for that moment.

  graph_to_text_record(graph) -> str
      Render the graph as a flat text record (for kf_memory backward compat).

Each function is a STUB. The autonomous worker (gemma3:27b) implements them
against the acceptance tests in tests/test_instance_brain_wire.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SCRIPTS = str(Path(__file__).resolve().parent)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import re  # noqa: E402

import instance_consolidate  # noqa: E402
import instance_graph  # noqa: E402
import instance_perceive  # noqa: E402
import node_merge  # noqa: E402
import perception_consensus  # noqa: E402
import screen_quarantine  # noqa: E402
import spatial_relations  # noqa: E402
import world_binder  # noqa: E402

_MAX_FRAMES = 500  # cap accumulation per moment


def perceive_and_graph(frame_path: str, moment: str, graphs_store: dict,
                       pose: dict | None = None,
                       depth_grid: dict | None = None) -> dict:
    """Run the instance pipeline on one frame AND bind across all frames.

    Per-frame: detector + per-crop VLM -> instances -> single-frame graph.
    Across frames the binder individuates by WORLD COORDINATE: when an ARKit
    depth-grid is present (spatial mode), each instance's box is projected to a
    world (x,y,z); instances at the same location = one node regardless of the
    VLM's inconsistent text; count = number of distinct nodes. Cross-frame
    CONSENSUS tiers one-off reads as provisional. Spatial RELATIONS between nodes
    are derived from geometry. Without depth (standard mode) it falls back to
    bearing-based consolidation. Result under "consolidated".
    """
    instances = instance_perceive.perceive(frame_path)
    # Quarantine on-screen reads: a "Nutella" read INSIDE the laptop box is screen
    # content (our chat), not a physical jar — it binds to the screen, not the world.
    instances = screen_quarantine.mark_on_screen(instances)
    graph = instance_graph.build_graph(instances)

    prev = graphs_store.get(moment) or {}
    frames = (prev.get("_frame_instances") or [])[-(_MAX_FRAMES - 1):]
    poses = (prev.get("_frame_poses") or [])[-(_MAX_FRAMES - 1):]
    grids = (prev.get("_frame_grids") or [])[-(_MAX_FRAMES - 1):]
    frames.append(instances)
    poses.append(pose)
    grids.append(depth_grid)

    graph["_frame_instances"] = frames
    graph["_frame_poses"] = poses
    graph["_frame_grids"] = grids
    # Count PHYSICAL objects only (drop screen-content reads from every frame).
    phys_frames = [screen_quarantine.physical_only(fr) for fr in frames]
    try:
        if any(g for g in grids):
            # World-coordinate binding (the real spatial substrate).
            bound = world_binder.bind_world_instances(phys_frames, grids)
            # Absorb estimated-depth jitter: collapse same-object nodes split by
            # coordinate wobble (no-LiDAR), without merging distinct brands.
            # Tight on the reliable bearing plane (x,y), looser on the noisy
            # estimated-depth axis (z). Stable band z in [0.18, 0.25] gave the
            # correct physical count on a real capture (3 nutella, 1 pesto, 1 pringles).
            bound = node_merge.merge_jittered(bound, radius_m=0.13, radius_z=0.22)
            tier_in = {"instances": bound["nodes"],
                       "counts_by_type": bound["counts_by_type"]}
            tiered = perception_consensus.tier_instances(tier_in, len(frames))
            tiered["relations"] = spatial_relations.relations(bound["nodes"])
            tiered["coordinate_bound"] = True
            _attach_identity(tiered.get("instances") or [])
            graph["consolidated"] = tiered
        else:
            # No depth yet (standard mode) -> bearing fallback.
            cons = instance_consolidate.consolidate_world(phys_frames, poses)
            graph["consolidated"] = perception_consensus.tier_instances(cons, len(frames))
    except Exception:
        graph["consolidated"] = None
    graphs_store[moment] = graph
    return graph


_COUNT_Q_RE = re.compile(r"how\s+many\s+(?P<noun>[a-z][a-z\s-]*?)s?\b", re.IGNORECASE)


def _singular(word: str) -> str:
    w = word.strip().lower()
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss") and len(w) > 1:
        return w[:-1]
    return w


def _count_answer_from_consolidated(question: str, consolidated: dict | None) -> dict | None:
    """If the question is 'how many X', answer from the consolidated cross-frame
    counts (the honest, deduped number) instead of an LLM guess off one frame."""
    if not consolidated:
        return None
    m = _COUNT_Q_RE.search(question)
    if not m:
        return None
    # Prefer the CONSENSUS-confirmed counts (objects seen in >=2 frames) — the
    # honest, hallucination-filtered number — falling back to raw counts.
    counts = (consolidated.get("confirmed_counts_by_type")
              or consolidated.get("counts_by_type") or {})
    noun = _singular(m.group("noun").split()[-1])  # last word, singularized

    # 1) TYPE match (detector type, e.g. "jar", "bottle").
    info = counts.get(noun)
    if info is None:
        for ctype, cinfo in counts.items():
            if ctype in noun or noun in ctype:
                info, noun = cinfo, ctype
                break
    if info is not None:
        # confirmed_counts_by_type uses plain ints; counts_by_type uses {distinct,hedge}.
        if isinstance(info, dict):
            distinct = info.get("distinct")
            hedge = str(info.get("hedge", distinct if distinct is not None else ""))
        else:
            distinct = info
            hedge = str(info)
        if "-" in hedge:
            ans = (f"I counted between {hedge} {noun}s across what I saw "
                   f"(I can't tell identical {noun}s apart without spatial depth, so it's a range).")
        else:
            ans = f"I counted {distinct} {noun}{'' if distinct == 1 else 's'} across what I saw."
        return {"answer": ans, "source": "instance_graph_consolidated", "refused": False,
                "consolidated_count": distinct, "hedge": hedge}

    # 2) BRAND/TEXT match (e.g. "how many nutellas" — count consolidated instances
    #    whose read text / brand / name / label contains the queried word).
    query = m.group("noun").strip().lower()
    qword = query.split()[-1]
    qstem = qword[:-1] if qword.endswith("s") and len(qword) > 3 else qword
    # Count brand matches among CONFIRMED instances (>=2 frames) when tiers exist,
    # else all instances. Demotes one-off hallucinated brand reads.
    all_inst = consolidated.get("instances") or []
    confirmed = [i for i in all_inst if i.get("tier") == "confirmed"]
    instances = confirmed if any(i.get("tier") for i in all_inst) else all_inst
    matches = []
    for inst in instances:
        parts = [str(inst.get(k, "")) for k in ("text", "brand", "name", "label", "type")]
        parts.extend(str(t) for t in (inst.get("texts") or []))  # every read this object got
        blob = " ".join(parts).lower()
        if qstem and qstem in blob:
            matches.append(inst)
    if matches:
        n = len(matches)
        label = qword
        return {"answer": f"I counted {n} {label}{'' if n == 1 else 's'} across what I saw.",
                "source": "instance_graph_consolidated", "refused": False,
                "consolidated_count": n, "hedge": str(n)}
    return None


def answer_from_graph(question: str, moment: str, graphs_store: dict,
                      ollama_host: str = "http://127.0.0.1:11434",
                      model: str = "gemma3:27b-it-qat") -> dict | None:
    """Answer a question from the stored instance graph, or return None.

    Steps:
      1. Look up graphs_store.get(moment). If missing or empty nodes, return None.
      2. Call instance_graph.render_graph(graph) to get the text summary.
      3. Call instance_graph.answer(graph, question) to get the LLM answer.
      4. Return a dict: {"answer": str, "source": "instance_graph",
         "refused": bool, "graph_nodes": int, "graph_edges": int}.
         Set refused=True if the answer contains 'I don't have' or similar refusal.
      5. Return None if there is no graph or the graph has zero nodes.

    """
    graph = graphs_store.get(moment)
    if not graph or not graph.get("nodes"):
        return None
    # Counting questions: answer from the CONSOLIDATED cross-frame count (deduped,
    # honest) rather than an LLM guess off the latest single frame.
    count_ans = _count_answer_from_consolidated(question, graph.get("consolidated"))
    if count_ans is not None:
        return count_ans
    # Spatial questions: answer from the geometric relations between world nodes.
    spatial_ans = _spatial_answer_from_relations(question, graph.get("consolidated"))
    if spatial_ans is not None:
        return spatial_ans
    instance_graph.render_graph(graph)
    ans = instance_graph.answer(graph, question)
    refused = "don't have" in ans.lower() or "do not have" in ans.lower()
    return {
        "answer": ans,
        "source": "instance_graph",
        "refused": refused,
        "graph_nodes": len(graph["nodes"]),
        "graph_edges": len(graph["edges"]),
    }


def _attach_identity(nodes: list) -> None:
    """Tag each node with its cross-frame identity consensus — reliable only when
    the per-crop reads AGREE across frames; a one-off misread ('scallops') is
    flagged unreliable so the brain hedges instead of asserting it."""
    try:
        import identity_consensus
    except Exception:
        return
    for n in nodes:
        try:
            ident = identity_consensus.resolve(list(n.get("texts") or []))
            n["identity"] = ident
            n["identity_reliable"] = identity_consensus.is_reliable(ident)
        except Exception:
            continue


_SPATIAL_Q_RE = re.compile(
    r"what(?:'s| is| was|s)?\s+(?P<rel>next to|to the left of|left of|to the right of|"
    r"right of|above|below|on top of|behind|in front of)\s+(?P<ref>.+?)\s*\??$",
    re.IGNORECASE,
)
_REL_ALIASES = {
    "to the left of": "left of", "to the right of": "right of",
}


def _spatial_answer_from_relations(question: str, consolidated: dict | None) -> dict | None:
    """Answer 'what is <relation> <X>' from the geometric relations between world nodes."""
    if not consolidated:
        return None
    relations = consolidated.get("relations") or []
    if not relations:
        return None
    m = _SPATIAL_Q_RE.search(question.strip())
    if not m:
        return None
    rel = _REL_ALIASES.get(m.group("rel").lower(), m.group("rel").lower())
    ref = m.group("ref").strip().lower()
    ref_stem = ref.split()[-1]
    hits = []
    for r in relations:
        a, b, rr = str(r.get("from", "")), str(r.get("to", "")), str(r.get("rel", "")).lower()
        if rr != rel:
            continue
        # relation r means: `from` is <rel> `to`. Asking "what is <rel> <ref>": ref is `to`.
        if ref_stem in b.lower() or ref in b.lower():
            hits.append((a, r.get("dist_m")))
    if not hits:
        return None
    parts = [f"{a}" + (f" ({d:.2f} m)" if isinstance(d, (int, float)) else "") for a, d in hits]
    ans = f"{', '.join(parts)} {('is' if len(hits) == 1 else 'are')} {rel} the {ref}."
    return {"answer": ans, "source": "instance_graph_spatial", "refused": False}


def graph_to_text_record(graph: dict) -> str:
    """Render a scene graph as a compact text block for kf_memory records.

    The brain server injects this into the flat kf_memory store so existing
    answer paths (inject_structure, ask_home) also benefit from instance data.

    Steps:
      1. Call instance_graph.render_graph(graph) if the graph has nodes.
      2. Return the rendered text.
      3. If graph has no nodes, return "".

    """
    if not graph.get("nodes"):
        return ""
    return instance_graph.render_graph(graph)
