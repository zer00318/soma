"""Acceptance spec for salience entity extraction (worker task: salience_entity)."""
from scripts.salience_helper import extract_entity


def test_named_person():
    assert extract_entity("appears to be the philosopher Kushal Mehra") == "Kushal Mehra"


def test_brand_logo():
    assert extract_entity("recognised the Adidas logo") == "Adidas"


def test_landmark():
    assert extract_entity("looks like the Eiffel Tower in the background") == "Eiffel Tower"


def test_no_entity():
    assert extract_entity("visible dust on the keyboard keys") == ""
    assert extract_entity("maybe a coffee stain") == ""
