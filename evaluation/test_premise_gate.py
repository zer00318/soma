#!/usr/bin/env python3
"""Tests for the deterministic premise-correction gate."""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import premise_gate


def test_corrects_wrong_emergency_number():
    res = {"answer": "112", "refused": False, "support": 4, "tally": {"112": 4}}

    correction = premise_gate.premise_correction(
        "What is the 911 emergency number on the sign?", res)

    assert correction is not None
    assert "Not 911" in correction
    assert "112" in correction


def test_no_false_correction_without_presupposed_number():
    res = {
        "answer": "1845 - 1923",
        "refused": False,
        "support": 5,
        "tally": {"1845 - 1923": 5},
    }

    assert premise_gate.premise_correction(
        "What years did R\u00f6ntgen live?", res) is None


def test_corrects_wrong_plaque_date():
    res = {
        "answer": "1881 - 1945",
        "refused": False,
        "support": 3,
        "tally": {"1881 - 1945": 3},
    }

    correction = premise_gate.premise_correction("Was the plaque dated 1899?", res)

    assert correction is not None
    assert "Not 1899" in correction


def test_corrects_gate_number_that_is_not_answer_prefix():
    res = {"answer": "112", "refused": False, "support": 3, "tally": {"112": 3}}

    correction = premise_gate.premise_correction("Is it gate 12?", res)

    assert correction is not None
    assert "Not 12" in correction
    assert "112" in correction


def test_refused_or_low_support_returns_none():
    refused = {
        "answer": "112",
        "refused": True,
        "support": 4,
        "tally": {"112": 4},
    }
    low_support = {
        "answer": "112",
        "refused": False,
        "support": 2,
        "tally": {"112": 2},
    }

    assert premise_gate.premise_correction("Is it 911?", refused) is None
    assert premise_gate.premise_correction("Is it 911?", low_support) is None


def test_true_premise_prefix_returns_none():
    res = {
        "answer": "1881 - 1945",
        "refused": False,
        "support": 3,
        "tally": {"1881 - 1945": 3},
    }

    assert premise_gate.premise_correction("the 1881 plaque", res) is None
