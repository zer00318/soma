from __future__ import annotations

from scripts.specialist_chess import answer, extract, identify_opening, parse_moves


def test_parse_moves_extracts_clean_san_sequence():
    assert parse_moves("1. e4 d5 2. exd5 Qxd5 3. Nc3") == ["e4", "d5", "exd5", "Qxd5", "Nc3"]


def test_identify_opening_matches_known_prefixes():
    assert identify_opening(["e4", "d5"]) == "Scandinavian Defense"
    assert identify_opening(["e4", "c5"]) == "Sicilian Defense"
    assert identify_opening(["d4", "Nf6"]) == "Indian Defense"
    assert identify_opening([]) == "Unknown opening"


def test_extract_identifies_scandinavian_and_move_count():
    facts = extract({"objects": [], "texts": ["1. e4 d5 2. exd5 Qxd5"], "caption": ""})

    assert facts["opening"] == "Scandinavian Defense"
    assert facts["move_count"] == 4
    assert facts["moves"] == ["e4", "d5", "exd5", "Qxd5"]


def test_extract_detects_win_result_marker():
    facts = extract({"objects": [], "texts": ["1. e4 d5 2. exd5 Qxd5 1-0"], "caption": ""})

    assert facts["result"] == "win"


def test_answer_reports_opening():
    facts = extract({"objects": [], "texts": ["1. e4 d5 2. exd5 Qxd5"], "caption": ""})

    result = answer(facts, "what opening did I play")

    assert result is not None
    assert "Scandinavian" in result["answer"]
    assert result["refused"] is False


def test_non_chess_question_returns_none():
    facts = extract({"objects": [], "texts": ["1. e4 d5 2. exd5 Qxd5"], "caption": ""})

    assert answer(facts, "how much soya") is None
