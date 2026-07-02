"""Acceptance spec for salience note tiering (worker task: salience_tiering).

Tiering is what keeps the 'what's interesting' helper HONEST: an interesting guess must
land in 'inferred', a recognised entity in 'recognized', a plain visible detail in
'observed' — so the brain never reports a guess as something definitely seen.
"""
from __future__ import annotations

from scripts.salience_helper import tier_salience


def test_inferred_is_hedged_without_named_entity():
    assert tier_salience("maybe the keyboard has some dirt") == "inferred"
    assert tier_salience("looks like a coffee stain on the desk") == "inferred"
    assert tier_salience("might be slightly out of place") == "inferred"


def test_recognized_named_entity_or_brand():
    assert tier_salience("appears to be the philosopher Kushal Mehra") == "recognized"
    assert tier_salience("recognised the Adidas logo") == "recognized"
    # recognition beats hedging: a hedged but specifically-named entity is 'recognized'
    assert tier_salience("looks like the Eiffel Tower in the background") == "recognized"


def test_observed_concrete_detail():
    assert tier_salience("there is visible dust on the keyboard keys") == "observed"
    assert tier_salience("a worn patch on the desk surface") == "observed"


def test_default_observed():
    assert tier_salience("a small sticker on the laptop lid") == "observed"
