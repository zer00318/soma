from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ax_adapter import container_path, elements_to_rows  # noqa: E402


def test_container_path_mirrors_the_physical_hierarchy():
    p = container_path("Brave Browser", "https://youtube.com/watch?v=x",
                       "AXWindow/AXGroup/AXWebArea/AXHeading")
    assert p == "display:main/app:Brave Browser/tab:https://youtube.com/watch?v=x/AXWebArea/AXHeading"
    # structural noise (AXWindow/AXGroup/?) is dropped; no url -> no tab node
    assert container_path("Xcode", None, "AXWindow/?/AXStaticText") == \
        "display:main/app:Xcode/AXStaticText"


def test_elements_become_graded_authoritative_rows():
    els = [
        {"role": "AXHeading", "text": "Rao Bahadur (2026) Telugu DVDS",
         "path": "AXWindow/AXWebArea/AXHeading", "pos": (10.0, 200.0), "size": (500.0, 40.0)},
        {"role": "AXTab", "text": "TEAMWORK DEATHRUN - YouTube",
         "path": "AXWindow/AXTabGroup/AXTab", "pos": None, "size": None},
    ]
    rows = elements_to_rows("Brave Browser", "https://other-site.example", els)
    assert len(rows) == 2
    head = rows[0]
    assert head["text"].startswith("AXEL | app=Brave Browser | url=https://other-site.example | role=AXHeading")
    assert head["provenance"]["grade"] == "authoritative"
    assert "AXWebArea/AXHeading" in head["provenance"]["container_path"]
    # THE founder case, now representable: the tab row and the heading row are
    # DIFFERENT containers — a brain can finally tell them apart.
    tab = rows[1]
    assert "AXTabGroup/AXTab" in tab["provenance"]["container_path"]
    assert tab["provenance"]["role"] == "AXTab"


def test_salience_cap_keeps_longest_texts():
    els = [{"role": "AXStaticText", "text": f"t{i}" * (i + 1),
            "path": "AXWindow/AXStaticText", "pos": None, "size": None}
           for i in range(40)]
    rows = elements_to_rows("App", None, els, max_rows=5)
    assert len(rows) == 5
    assert all(len(r["text"]) > 60 for r in rows)  # the longest survived
