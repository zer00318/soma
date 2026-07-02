from __future__ import annotations

import pytest

from scripts.context_reconciler import (
    phrase_uncertainty,
    reconcile,
    reconcile_identity,
    reconcile_node,
)


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


def test_reconcile_identity_picks_most_frequent_offline() -> None:
    result = reconcile_identity(["Doritos", "Doritos", "Chip bag", "Face mask"])

    assert result["primary"] == "Doritos"
    assert result["confidence"] > 0.4
    assert "Chip bag" in result["variants"]
    assert "Doritos" not in result["variants"]


def test_reconcile_identity_drops_generic_only_reads() -> None:
    # "object"/"thing"/"item" are generic; with nothing else there is no identity.
    result = reconcile_identity(["object", "thing", "item"])

    assert result["primary"] is None
    assert result["variants"] == []


def test_reconcile_identity_preserves_surface_form() -> None:
    result = reconcile_identity(["PRINGLES", "Pringles can"])

    # First-seen original casing is kept for display.
    assert result["primary"] == "PRINGLES"


def test_reconcile_identity_uses_plausibility_when_provided() -> None:
    result = reconcile_identity(
        ["rocks", "soya", "soya"],
        activity="cooking",
        plausibility_fn=stub_plausibility,
    )

    assert result["primary"] == "soya"
    assert "rocks" not in result["variants"]


def test_reconcile_attaches_reconciled_result_and_updates_identity() -> None:
    nodes = [{"texts": ["rocks", "soya", "soya"], "identity": "paper bag"}]

    result = reconcile(nodes, "cooking", stub_plausibility)

    assert result[0]["reconciled"]["chosen"] == "soya"
    assert result[0]["identity"] == "soya"
