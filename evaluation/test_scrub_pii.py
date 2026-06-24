#!/usr/bin/env python3
"""Fast tests for the standalone local PII scrubber."""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from scrub_pii import scrub_pii, scrub_record


def test_scrubs_email():
    assert scrub_pii("email me at a.b@x.de") == "email me at [redacted]"


def test_scrubs_international_and_grouped_phone_numbers():
    assert scrub_pii("call +49 89 289 112") == "call [redacted]"
    assert scrub_pii("089 289 112") == "[redacted]"


def test_keeps_year_ranges():
    assert scrub_pii("Röntgen 1845 - 1923") == "Röntgen 1845 - 1923"


def test_keeps_truncated_and_dense_year_ranges():
    # OCR truncates the second year as the camera walks past the plaque — the
    # grouped-phone heuristic must NOT eat these (regression: '1845 - 192').
    assert scrub_pii("1845 - 192") == "1845 - 192"
    assert scrub_pii("Robert Sauer 1898-1970") == "Robert Sauer 1898-1970"


def test_keeps_short_numbers_prices_and_gate_numbers():
    assert scrub_pii("room 042") == "room 042"
    assert scrub_pii("2 €") == "2 €"
    assert scrub_pii("gate 12") == "gate 12"


def test_scrubs_iban():
    assert scrub_pii("IBAN DE89370400440532013000") == "IBAN [redacted]"


def test_scrub_record_scrubs_ocr_list_and_keeps_names():
    rec = scrub_record({"ocr": ["a@b.com", "WILHELM CONRAD RÖNTGEN"]})

    assert rec == {"ocr": ["[redacted]", "WILHELM CONRAD RÖNTGEN"]}
