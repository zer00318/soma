from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.mac_screen_daemon import (  # noqa: E402
    excluded,
    format_screen_text,
    should_emit,
)


def test_dedupe_emits_only_on_meaningful_change():
    # realistic screen: ~100 distinct tokens, like a real terminal or editor
    words = [f"word{i}" for i in range(100)]
    a = "SCREEN | app=Terminal window=zsh | text: " + " ".join(words)
    assert should_emit(None, a) is True          # first sighting always emits
    assert should_emit(a, a) is False            # identical screen is silent
    tweaked = a.replace("word50", "word999")     # clock-tick drift stays silent
    assert should_emit(a, tweaked) is False
    changed = "SCREEN | app=Terminal window=zsh | text: Traceback ValueError in episodes.py line 90"
    assert should_emit(a, changed) is True       # real change emits
    assert should_emit(a, "   ") is False        # blank OCR never emits


def test_trace_windows_are_excluded():
    assert excluded("TRACE", "anything") is True
    assert excluded("Safari", "TRACE — ask your memory") is True
    assert excluded("Safari", "apple.com") is False


def test_screen_text_is_bounded_and_tagged():
    text = format_screen_text("Xcode", "FastVLM App.xcodeproj", ["Build Succeeded", "0 warnings"])
    assert text.startswith("SCREEN | app=Xcode window=FastVLM App.xcodeproj")
    assert "Build Succeeded ; 0 warnings" in text
    long = format_screen_text("A", "B", ["x" * 500, "y" * 500])
    assert len(long) < 1000 and long.endswith("…")


def test_region_banding_separates_play_from_chrome():
    from scripts.mac_screen_daemon import region_of
    assert region_of(0.5, 0.05) == "top-chrome"    # tab strip: another site's title
    assert region_of(0.5, 0.5) == "main"           # the thing actually playing
    assert region_of(0.9, 0.5) == "right-rail"     # recommendations / queue
    assert region_of(0.1, 0.5) == "left-rail"
    assert region_of(0.5, 0.97) == "bottom-chrome"


def test_spans_attribute_to_topmost_containing_window():
    from scripts.mac_screen_daemon import attribute_spans
    windows = [
        {"x": 0, "y": 0, "w": 800, "h": 600, "front": True},    # front window
        {"x": 0, "y": 0, "w": 1600, "h": 1000, "front": False}, # behind, larger
    ]
    spans = [("video title", 400, 300), ("background text", 1200, 500),
             ("floating", 5000, 5000)]
    out = attribute_spans(spans, windows)
    assert out[0] == ("video title", 0, "main")       # front window wins z-order
    assert out[1][1] == 1                             # back window catches its own
    assert out[2] == ("floating", None, "desktop")    # nowhere = honest desktop
