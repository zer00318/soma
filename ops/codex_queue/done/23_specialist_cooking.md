# CODEX BRIEF 23 — cooking domain specialist (the soya case)

Branch: `codex/23-cooking`. Python via `.venv/bin/python`. Create ONE new module
`scripts/specialist_cooking.py` + tests `tests/test_specialist_cooking.py`. Do NOT edit other files.

## Why
When the activity is cooking, extract DOMAIN structure generic OCR can't: which INGREDIENT, in which
UTENSIL, roughly HOW MUCH, and what ACTION — so "how much soya would I use?" is answerable later.
The deterministic PARSING + hedging logic is what this module owns; an injected describe function
(a VLM call, passed in) supplies the raw reading so tests stay deterministic.

## The module: `scripts/specialist_cooking.py`

```python
INGREDIENT_WORDS = {"soya","soy","flour","rice","sugar","salt","oil","lentil","dal","bean","spice",
                    "pepper","onion","garlic","tomato","pasta","nutella","pesto","water","milk","egg"}
UTENSIL_WORDS = {"bowl","cup","spoon","tablespoon","teaspoon","pan","pot","jar","glass","scoop",
                 "plate","container","measuring cup"}
# Rough volume priors (ml) for "a full <utensil>" — used to hedge a quantity when no scale/label.
UTENSIL_VOLUME_ML = {"teaspoon":5,"tablespoon":15,"cup":240,"glass":250,"bowl":500,"scoop":60,
                     "spoon":15,"jar":400,"pot":2000,"pan":1500}

def extract(perception, fill_fraction=0.5):
    """Extract structured cooking facts from a frame/moment's perception.

    perception = {"objects":[str], "texts":[str], "caption": str}.
    Returns:
      {
        "ingredients": [ {"name": str, "in": <utensil or None>,
                          "amount_ml": <int estimate or None>,
                          "amount_hedge": <str, e.g. "~half a bowl (≈250 ml), rough">} ],
        "utensils": [str],
        "summary": str,
      }
    Logic:
      - Find ingredient words (in objects/texts/caption). For each, find the NEAREST utensil mentioned
        (first utensil in the same perception) as its container.
      - If an utensil is known, estimate amount_ml = round(UTENSIL_VOLUME_ML[utensil] * fill_fraction)
        and write a clearly HEDGED amount string ("rough, no scale"). If no utensil/label, amount None
        and hedge "amount not measurable from what I saw".
      - If a TEXT has an explicit weight/volume (regex '\\d+\\s?(g|kg|ml|l)'), prefer it verbatim.
    Honest: never assert a precise number the data can't support — always hedge estimates.
    """

def answer(cooking_facts, question):
    """Answer a cooking question from extracted facts, or return None if not a cooking question.
    Handle 'how much <ingredient>' -> the ingredient's amount_hedge (or honest 'I can't measure it
    reliably'); 'what did I cook/use' -> list ingredients. Return {"answer":str,"refused":bool} or None.
    """
```

## Acceptance tests (`tests/test_specialist_cooking.py`)
1. perception objects ["bowl"], texts ["soya"] -> ingredients has soya in="bowl",
   amount_ml ≈ 250 (bowl 500 * 0.5), amount_hedge mentions "rough".
2. texts ["soya","200 g"] -> the 200 g is used verbatim in the hedge (explicit label beats estimate).
3. ingredient with NO utensil -> amount_ml None, hedge says not measurable.
4. answer(facts, "how much soya would I use") -> mentions the hedged amount, refused False.
5. answer(facts, "how much rice") when no rice present -> honest 'I didn't see rice', refused True.
6. answer(facts, "what's the weather") -> None (not a cooking question).

## Guardrails
- Pure, deterministic, no I/O / network / LLM (the VLM reading is upstream; this parses it).
  `pytest tests/ -q` green. Commit on branch. Report results + the soya example output.
