#!/usr/bin/env python3
"""Pure helper tests for assembler honesty guards."""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ask_home


def test_question_subject_grounded_refuses_absent_subject():
    assert not ask_home._question_subject_grounded(
        "What was the price of the coffee?",
        "2 EUR 3 EUR entrance plaque",
    )


def test_question_subject_grounded_accepts_present_name():
    assert ask_home._question_subject_grounded(
        "What years next to Robert Sauer?",
        "ROBERT SAUER 1898 - 1970",
    )


def test_question_subject_grounded_accepts_present_sign():
    assert ask_home._question_subject_grounded(
        "What is on the sign?",
        "WILHELM CONRAD R\u00d6NTGEN sign",
    )


def test_question_subject_grounded_accepts_plural_trim():
    assert ask_home._question_subject_grounded(
        "What text was on the signs?",
        "one sign read EXIT",
    )
