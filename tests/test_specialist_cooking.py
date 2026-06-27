from __future__ import annotations

from scripts.specialist_cooking import answer, extract


def test_extract_estimates_soya_in_bowl():
    facts = extract({"objects": ["bowl"], "texts": ["soya"], "caption": ""})

    assert facts["ingredients"] == [
        {
            "name": "soya",
            "in": "bowl",
            "amount_ml": 250,
            "amount_hedge": "~half a bowl (≈250 ml), rough visual estimate, no scale.",
        }
    ]
    assert facts["utensils"] == ["bowl"]
    assert "rough" in facts["ingredients"][0]["amount_hedge"].lower()


def test_extract_prefers_explicit_weight_text():
    facts = extract({"objects": [], "texts": ["soya", "200 g"], "caption": ""})

    ingredient = facts["ingredients"][0]
    assert ingredient["name"] == "soya"
    assert ingredient["amount_ml"] is None
    assert "200 g" in ingredient["amount_hedge"]


def test_extract_without_utensil_is_not_measurable():
    facts = extract({"objects": [], "texts": ["soya"], "caption": ""})

    ingredient = facts["ingredients"][0]
    assert ingredient["in"] is None
    assert ingredient["amount_ml"] is None
    assert "not measurable" in ingredient["amount_hedge"].lower()


def test_answer_how_much_soya_uses_hedged_amount():
    facts = extract({"objects": ["bowl"], "texts": ["soya"], "caption": ""})

    result = answer(facts, "how much soya would I use")

    assert result == {
        "answer": "For soya, ~half a bowl (≈250 ml), rough visual estimate, no scale.",
        "refused": False,
    }


def test_answer_missing_rice_is_honest_refusal():
    facts = extract({"objects": ["bowl"], "texts": ["soya"], "caption": ""})

    result = answer(facts, "how much rice")

    assert result == {"answer": "I didn't see rice.", "refused": True}


def test_non_cooking_question_returns_none():
    facts = extract({"objects": ["bowl"], "texts": ["soya"], "caption": ""})

    assert answer(facts, "what's the weather") is None
