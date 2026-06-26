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

_MAX_FRAMES = 500  # cap accumulation per moment


def perceive_and_graph(frame_path: str, moment: str,
                       graphs_store: dict, yaw: float | None = None) -> dict:
    """Run the instance pipeline on one frame AND consolidate across all frames.

    Per-frame: detector + per-crop VLM -> instances -> single-frame graph
    (nodes/edges/relations from geometry). Across frames: accumulate every
    frame's instances + camera yaw and run the cross-frame consolidator so the
    SAME physical object seen in many frames counts ONCE. The returned graph is
    the latest single-frame graph (for relations + backward compat) with the
    consolidated cross-frame result attached under "consolidated".

    """
    instances = instance_perceive.perceive(frame_path)
    graph = instance_graph.build_graph(instances)

    prev = graphs_store.get(moment) or {}
    frames = (prev.get("_frame_instances") or [])[-(_MAX_FRAMES - 1):]
    yaws = (prev.get("_frame_yaws") or [])[-(_MAX_FRAMES - 1):]
    frames.append(instances)
    yaws.append(yaw)

    graph["_frame_instances"] = frames
    graph["_frame_yaws"] = yaws
    try:
        graph["consolidated"] = instance_consolidate.consolidate(frames, yaws)
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
    counts = consolidated.get("counts_by_type") or {}
    noun = _singular(m.group("noun").split()[-1])  # last word, singularized

    # 1) TYPE match (detector type, e.g. "jar", "bottle").
    info = counts.get(noun)
    if info is None:
        for ctype, cinfo in counts.items():
            if ctype in noun or noun in ctype:
                info, noun = cinfo, ctype
                break
    if info is not None:
        hedge = str(info.get("hedge", info.get("distinct", "")))
        distinct = info.get("distinct")
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
    instances = consolidated.get("instances") or []
    matches = []
    for inst in instances:
        blob = " ".join(str(inst.get(k, "")) for k in ("text", "brand", "name", "label", "type")).lower()
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
