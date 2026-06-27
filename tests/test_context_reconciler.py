from __future__ import annotations

import pytest

from scripts.context_reconciler import phrase_uncertainty, reconcile, reconcile_node


PLAUSIBILITY = {
    "cooking": {
        "soya": 0.9,
        "scallops": 0.4,
        "paper bag": 0.5,
        "rocks": 0.05,
    }
}


def stub_plausibility(candidate: str, activity: str) -> float:
    return PLAUSIBILITY.get(activity, {}).get(candidate, 0.3)


def test_reconcile_node_prefers_plausible_candidate_with_activity_prior() -> None:
    result = reconcile_node(["rocks", "soya", "soya", "paper bag"], "cooking", stub_plausibility)

    assert result["chosen"] == "soya"
    assert "rocks" in result["dropped"]


def test_reconcile_node_returns_none_when_only_candidate_is_implausible() -> None:
    result = reconcile_node(["rocks"], "cooking", stub_plausibility)

    assert result["chosen"] is None
    assert result["reliable"] is False
    assert result["confidence"] == 0.0


def test_reconcile_node_marks_repeated_single_candidate_as_reliable() -> None:
    result = reconcile_node(["soya", "soya", "soya"], "cooking", stub_plausibility)

    assert result["reliable"] is True
    assert result["confidence"] == pytest.approx(1.0)


def test_phrase_uncertainty_hedges_when_reconciled_identity_is_not_reliable() -> None:
    phrased = phrase_uncertainty({"chosen": "soya", "reliable": False}, "~250 ml")

    assert phrased == "I'm not certain it was soya, but if it was, ~250 ml"


def test_phrase_uncertainty_returns_detail_when_reconciled_identity_is_reliable() -> None:
    phrased = phrase_uncertainty({"chosen": "soya", "reliable": True}, "~250 ml")

    assert phrased == "~250 ml"


def test_reconcile_attaches_reconciled_result_and_updates_identity() -> None:
    nodes = [{"texts": ["rocks", "soya", "soya"], "identity": "paper bag"}]

    result = reconcile(nodes, "cooking", stub_plausibility)

    assert result[0]["reconciled"]["chosen"] == "soya"
    assert result[0]["identity"] == "soya"
