#!/usr/bin/env python3
"""Behavioral tests for the consensus-recall core — the honesty guarantees in code.

Run: .venv/bin/python evaluation/test_consensus_recall.py   (no model needed; the
answerer is a deterministic stub so these assert the CONSENSUS logic, not the LLM.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import consensus_recall as cr


def date_answerer(prompt):
    """Stub LLM honoring the prompt contract: for a year/date question, return the
    NNNN-NNNN range if present, else REFUSE (do not substitute a nearby name)."""
    ctx = prompt.split("--- WHAT YOU READ ---\n", 1)[1].split("\n---", 1)[0]
    import re
    m = re.search(r"\d{4}\s*-\s*\d{4}", ctx)
    return m.group(0) if m else cr.REFUSAL


def name_answerer(prompt):
    ctx = prompt.split("--- WHAT YOU READ ---\n", 1)[1].split("\n---", 1)[0]
    lines = [l for l in ctx.splitlines() if l.strip()]
    return max(lines, key=len) if lines else cr.REFUSAL


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    assert cond, name


def test_truncation_folds_into_complete():
    """The signature failure: one frame reads '188', neighbours read '1881 - 1945'.
    Consensus must answer the COMPLETE value, not the truncation."""
    scenes = [
        {"t": 80.0, "ocr": ["HANS FISCHER", "188"]},
        {"t": 80.5, "ocr": ["HANS FISCHER", "1881 - 1945"]},
        {"t": 81.0, "ocr": ["1881 - 1945"]},
    ]
    r = cr.consensus_read(scenes, "What years are on the sign?", date_answerer,
                          center=80.5, half=3, minrep=2)
    check("truncation -> complete date", r["answer"] == "1881 - 1945" and not r["refused"])


def test_numeric_value_does_not_fold_into_street_text():
    scenes = [
        {"t": 10.0, "ocr": ["1881"]},
        {"t": 10.5, "ocr": ["1881"]},
        {"t": 11.0, "ocr": ["1881 Hauptstrasse"]},
    ]
    r = cr.consensus_read(scenes, "What number is shown?", name_answerer,
                          center=10.5, half=3, minrep=3)
    check("bare number stays separate from street text",
          r["answer"] != "1881 Hauptstrasse"
          and r["tally"].get("1881") == 2
          and r["tally"].get("1881 hauptstrasse") == 1)


def test_numeric_prefix_truncation_folds_into_full_number():
    scenes = [
        {"t": 20.0, "ocr": ["089 289"]},
        {"t": 20.5, "ocr": ["089 289"]},
        {"t": 21.0, "ocr": ["089 289 112"]},
    ]
    r = cr.consensus_read(scenes, "What phone number is shown?", name_answerer,
                          center=20.5, half=3, minrep=3)
    check("numeric prefix truncation -> full number",
          r["answer"] == "089 289 112"
          and not r["refused"]
          and r["support"] == 3)


def test_one_off_garble_refuses():
    """Cursive the camera can't read -> random per-frame garble, no consensus ->
    the memory must stay SILENT rather than emit a confident lie."""
    scenes = [
        {"t": 40.0, "ocr": ["Mr Men rest"]},
        {"t": 40.5, "ocr": ["Are then fres"]},
        {"t": 41.0, "ocr": ["Ar. He finest"]},
    ]
    r = cr.consensus_read(scenes, "What name is written in cursive?", name_answerer,
                          center=40.5, half=3, minrep=3)
    check("illegible cursive -> refuse", r["refused"])


def test_consensus_name_wins():
    scenes = [
        {"t": 63.5, "ocr": ["WILHELM CONRAD RÖNTGEN", "noise here"]},
        {"t": 64.0, "ocr": ["WILHELM CONRAD RÖNTGEN"]},
        {"t": 64.5, "ocr": ["WILHELM CONRAD RÖNTGEN"]},
        {"t": 65.0, "ocr": ["M CONRAD RONTGEN"]},
    ]
    r = cr.consensus_read(scenes, "What is the name on the sign?", name_answerer,
                          center=64.0, half=3, minrep=3)
    check("repeated name -> answered", "RÖNTGEN" in r["answer"] and not r["refused"])


def test_keyboard_noise_never_answers():
    """Keyboard rows off the laptop body must be filtered before they can win."""
    scenes = [
        {"t": 10.0, "ocr": ["command option control", "3 # 2 € W Q"]},
        {"t": 10.5, "ocr": ["command option", "Z X C"]},
        {"t": 11.0, "ocr": ["esc fn shift"]},
    ]
    r = cr.consensus_read(scenes, "What is written on the screen?", name_answerer,
                          center=10.5, half=3, minrep=2)
    check("keyboard rows -> refuse", r["refused"])


def test_date_single_clean_sighting_passes():
    """A NNNN-NNNN date is structurally not a misread: one clean read may pass even
    below minrep (the rest of the frames couldn't see the bottom-edge date)."""
    scenes = [
        {"t": 46.0, "ocr": ["ROBERT SAUER", "1898 - 1970"]},
        {"t": 46.5, "ocr": ["ROBERT SAUER"]},
        {"t": 47.0, "ocr": ["ROBERT SA"]},
    ]
    r = cr.consensus_read(scenes, "What years are listed next to Robert Sauer?",
                          date_answerer, center=46.0, half=3, minrep=3)
    check("clean single date -> answered", r["answer"] == "1898 - 1970" and not r["refused"])


def test_empty_memory_refuses():
    r = cr.consensus_read([], "Anything?", name_answerer, center=0, half=5, minrep=2)
    check("empty memory -> refuse", r["refused"])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} consensus-recall behavior tests\n")
    for t in tests:
        t()
    print(f"\nAll {len(tests)} tests passed.")
