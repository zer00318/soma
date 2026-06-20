from __future__ import annotations

from soma.application.grounding_gate import REFUSAL_TEXT, ground

_CORPUS = (
    "A blue backpack rests on the wooden desk beside a red ceramic mug. "
    "Sunlight falls across the keyboard near the window."
)


def test_grounded_draft_is_asserted() -> None:
    draft = "The blue backpack sits on the wooden desk next to the ceramic mug."

    decision, text = ground(draft, _CORPUS)

    assert decision == "assert"
    assert text == draft


def test_fabricated_draft_is_refused() -> None:
    draft = "The golden trophy stood inside the marble fountain near the orchestra."

    decision, text = ground(draft, _CORPUS)

    assert decision == "refuse"
    assert text == REFUSAL_TEXT


def test_empty_draft_is_refused() -> None:
    decision, text = ground("   ", _CORPUS)

    assert decision == "refuse"
    assert text == REFUSAL_TEXT


def test_short_uncommitted_draft_is_asserted() -> None:
    # Fewer than three distinctive content tokens: not enough of a claim to refuse.
    decision, text = ground("I know.", _CORPUS)

    assert decision == "assert"
    assert text == "I know."
