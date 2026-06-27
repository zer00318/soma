from __future__ import annotations

from scripts.specialist_reading import answer, extract


def test_extract_pulls_title_and_salient_numbers():
    facts = extract(
        {
            "objects": [],
            "texts": ["Effects of Vitamin D", "The study used 2000 IU daily", "dose 50 mg"],
            "caption": "",
        }
    )

    assert "50 mg" in facts["numbers"]
    assert facts["title"] is not None
    assert "Vitamin D" in facts["title"]


def test_answer_reports_dose_when_present():
    facts = extract(
        {
            "objects": [],
            "texts": ["Effects of Vitamin D", "The study used 2000 IU daily", "dose 50 mg"],
            "caption": "",
        }
    )

    result = answer(facts, "what dose did it mention")

    assert result is not None
    assert "50 mg" in result["answer"]
    assert result["refused"] is False


def test_answer_reports_article_gist():
    facts = extract(
        {
            "objects": [],
            "texts": ["Effects of Vitamin D", "The study used 2000 IU daily", "dose 50 mg"],
            "caption": "",
        }
    )

    result = answer(facts, "what was the article about")

    assert result is not None
    assert "Effects of Vitamin D" in result["answer"]
    assert "2000 IU daily" in result["answer"]
    assert result["refused"] is False


def test_answer_refuses_honestly_when_no_numbers_exist():
    facts = extract({"objects": [], "texts": ["Effects of Vitamin D", "Background discussion only"], "caption": ""})

    result = answer(facts, "what number")

    assert result == {
        "answer": "I didn't capture any numeric dose or quantity from that reading.",
        "refused": True,
    }


def test_extract_picks_up_named_person_entities():
    facts = extract(
        {
            "objects": [],
            "texts": ["Interview with Robert Sauer", "Robert Sauer discussed memory recall."],
            "caption": "",
        }
    )

    assert "Robert Sauer" in facts["entities"]


def test_non_reading_question_returns_none():
    facts = extract({"objects": [], "texts": ["Effects of Vitamin D", "dose 50 mg"], "caption": ""})

    assert answer(facts, "how much soya") is None
