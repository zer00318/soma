from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from identity_consensus import is_reliable, resolve  # noqa: E402


def test_resolve_prefers_consensus_brand_identity() -> None:
    consensus = resolve(["Nutella", "nutella", "Nutella jar", "Hazelnut spread"])

    assert consensus["label"] == "nutella"
    assert consensus["tier"] == "high"
    assert consensus["agreement"] == 1.0
    assert consensus["alternatives"] == []


def test_resolve_flags_disagreement_as_low_reliability() -> None:
    consensus = resolve(["soya", "scallops", "paper bag", "snack"])

    assert consensus["tier"] == "low"
    assert consensus["agreement"] == 1 / 3
    assert is_reliable(consensus) is False


def test_resolve_strips_generic_container_suffix_from_supported_label() -> None:
    consensus = resolve(["Pringles", "Pringles", "Pringles can"])

    assert consensus["label"] == "pringles"
    assert consensus["tier"] == "high"
    assert consensus["agreement"] == 1.0


def test_resolve_all_generic_reads_stays_low_confidence() -> None:
    consensus = resolve(["jar", "bottle", "container"])

    assert consensus["tier"] == "low"
    assert consensus["agreement"] == 0.0
    assert is_reliable(consensus) is False


def test_resolve_empty_reads_returns_low_confidence_unknown() -> None:
    consensus = resolve([])

    assert consensus["label"] == ""
    assert consensus["tier"] == "low"
    assert consensus["agreement"] == 0.0
    assert consensus["alternatives"] == []
    assert is_reliable(consensus) is False


def test_resolve_reports_sorted_runner_up_alternatives() -> None:
    consensus = resolve(["pesto", "pesto", "pesto", "pringles", "pringles", "nutella"])

    assert consensus["label"] == "pesto"
    assert consensus["alternatives"] == [("pringles", 2), ("nutella", 1)]
