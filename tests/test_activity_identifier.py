from __future__ import annotations

from scripts.activity_identifier import identify


def test_cooking_activity_from_objects_and_texts():
    result = identify({"objects": ["bowl", "knife"], "texts": ["soya", "flour"]})

    assert result["activity"] == "cooking"
    assert result["specialists"] == ["cooking"]
    assert result["confidence"] > 0.5
    assert set(result["cues_hit"]) == {"bowl", "knife", "soya", "flour"}


def test_chess_activity_from_caption_and_site_text():
    result = identify({"caption": "playing lichess, white to move", "texts": ["chess.com"]})

    assert result["activity"] == "chess"
    assert result["specialists"] == ["chess"]


def test_reading_activity_from_book_and_article_caption():
    result = identify({"objects": ["book"], "caption": "reading a long article about history"})

    assert result["activity"] == "reading"
    assert result["specialists"] == ["document"]


def test_coding_activity_from_code_text_and_editor_caption():
    result = identify({"texts": ["def main()", "import os"], "caption": "code editor terminal"})

    assert result["activity"] == "coding"
    assert result["specialists"] == ["code"]


def test_generic_when_nothing_matches():
    result = identify({"objects": ["wall", "floor"]})

    assert result["activity"] == "generic"
    assert result["specialists"] == []
    assert result["ranked"] == []
    assert result["cues_hit"] == []


def test_cooking_beats_chess_when_it_has_more_cues():
    result = identify({"objects": ["bowl", "knife"], "texts": ["soya", "pawn"]})

    assert result["activity"] == "cooking"
    assert result["specialists"] == ["cooking"]
    assert result["ranked"][0] == ("cooking", 3)
    assert ("chess", 1) in result["ranked"]
