"""Acceptance tests for the instance-pipeline-to-brain bridge.

These tests exercise the bridge functions WITHOUT heavy deps (no torch, no
Grounding-DINO, no Ollama). They mock instance_perceive and instance_graph
to verify the WIRING is correct: perceive_and_graph stores the graph,
answer_from_graph reads it, graph_to_text_record renders it.
"""
from __future__ import annotations

from unittest import mock

from scripts.instance_brain_wire import (
    answer_from_graph,
    graph_to_text_record,
    perceive_and_graph,
)

# -- fixtures ---------------------------------------------------------------

FAKE_INSTANCES = [
    {"box": [0, 0, 100, 100], "det_label": "jar", "name": "Nutella",
     "text": "Nutella 400g", "colour": "brown", "material": "glass",
     "state": "closed", "orient": "upright"},
    {"box": [120, 0, 220, 100], "det_label": "jar", "name": "Barilla Pesto",
     "text": "Barilla", "colour": "green", "material": "glass",
     "state": "full", "orient": "upright"},
]

FAKE_GRAPH = {
    "nodes": [
        {"id": 0, "type": "jar", "name": "Nutella", "text": "Nutella 400g",
         "colour": "brown", "material": "glass", "state": "closed",
         "orient": "upright", "box": [0, 0, 100, 100], "category": "food"},
        {"id": 1, "type": "jar", "name": "Barilla Pesto", "text": "Barilla",
         "colour": "green", "material": "glass", "state": "full",
         "orient": "upright", "box": [120, 0, 220, 100], "category": "food"},
    ],
    "edges": [{"from": 0, "to": 1, "rel": "next_to"}],
    "counts": {"jar": 2},
}


# -- perceive_and_graph ------------------------------------------------------

@mock.patch("scripts.instance_brain_wire.instance_perceive")
@mock.patch("scripts.instance_brain_wire.instance_graph")
def test_perceive_stores_graph(mock_ig, mock_ip):
    mock_ip.perceive.return_value = FAKE_INSTANCES
    mock_ig.build_graph.return_value = FAKE_GRAPH

    store = {}
    result = perceive_and_graph("/tmp/test.jpg", "m1", store)

    mock_ip.perceive.assert_called_once_with("/tmp/test.jpg")
    mock_ig.build_graph.assert_called_once_with(FAKE_INSTANCES)
    assert store["m1"] is FAKE_GRAPH
    assert result is FAKE_GRAPH


@mock.patch("scripts.instance_brain_wire.instance_perceive")
@mock.patch("scripts.instance_brain_wire.instance_graph")
def test_perceive_overwrites_previous(mock_ig, mock_ip):
    mock_ip.perceive.return_value = FAKE_INSTANCES
    mock_ig.build_graph.return_value = FAKE_GRAPH

    store = {"m1": {"nodes": [], "edges": [], "counts": {}}}
    perceive_and_graph("/tmp/test.jpg", "m1", store)
    assert store["m1"] is FAKE_GRAPH


# -- answer_from_graph -------------------------------------------------------

def test_answer_returns_none_when_no_graph():
    assert answer_from_graph("how many jars?", "m1", {}) is None


def test_answer_returns_none_when_empty_graph():
    store = {"m1": {"nodes": [], "edges": [], "counts": {}}}
    assert answer_from_graph("how many jars?", "m1", store) is None


@mock.patch("scripts.instance_brain_wire.instance_graph")
def test_answer_returns_dict_when_graph_exists(mock_ig):
    mock_ig.render_graph.return_value = "INSTANCES: ..."
    mock_ig.answer.return_value = "Nutella and Barilla Pesto."

    # Clean graph with no consolidated data -> non-counting question uses the LLM path.
    clean_graph = {
        "nodes": [{"id": 0, "type": "jar"}, {"id": 1, "type": "jar"}],
        "edges": [{"from": 0, "to": 1, "rel": "next_to"}],
        "counts": {"jar": 2},
    }
    store = {"m1": clean_graph}
    result = answer_from_graph("what brands are on the table?", "m1", store)

    assert result is not None
    assert result["answer"] == "Nutella and Barilla Pesto."
    assert result["source"] == "instance_graph"


def test_counting_uses_consolidated_cross_frame_count():
    # A 'how many' question must answer from the deduped cross-frame consolidation,
    # not an LLM guess off one frame.
    graph = {
        "nodes": [{"id": 0, "type": "jar"}],
        "edges": [],
        "consolidated": {
            "counts_by_type": {"jar": {"distinct": 3, "hedge": "3"}},
            "instances": [], "summary": "jar 3",
        },
    }
    result = answer_from_graph("how many jars were there?", "m1", {"m1": graph})
    assert result is not None
    assert result["source"] == "instance_graph_consolidated"
    assert result["consolidated_count"] == 3
    assert "3 jars" in result["answer"]


def test_counting_hedges_when_indistinguishable():
    graph = {
        "nodes": [{"id": 0, "type": "cup"}],
        "edges": [],
        "consolidated": {
            "counts_by_type": {"cup": {"distinct": 4, "hedge": "1-4"}},
            "instances": [], "summary": "cup 1-4",
        },
    }
    result = answer_from_graph("how many cups?", "m1", {"m1": graph})
    assert result is not None
    assert "1-4" in result["answer"]
    assert result["source"] == "instance_graph_consolidated"


@mock.patch("scripts.instance_brain_wire.instance_graph")
def test_answer_detects_refusal(mock_ig):
    mock_ig.render_graph.return_value = "INSTANCES: ..."
    mock_ig.answer.return_value = "I don't have that in what I saw."

    store = {"m1": FAKE_GRAPH}
    result = answer_from_graph("what colour is the cat?", "m1", store)

    assert result is not None
    assert result["refused"] is True


# -- graph_to_text_record ----------------------------------------------------

@mock.patch("scripts.instance_brain_wire.instance_graph")
def test_text_record_renders_graph(mock_ig):
    mock_ig.render_graph.return_value = "INSTANCES: jar Nutella, jar Pesto"
    result = graph_to_text_record(FAKE_GRAPH)
    assert "Nutella" in result
    mock_ig.render_graph.assert_called_once_with(FAKE_GRAPH)


def test_text_record_empty_for_no_nodes():
    assert graph_to_text_record({"nodes": [], "edges": [], "counts": {}}) == ""
