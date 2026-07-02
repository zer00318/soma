# CODEX BRIEF 25 — reading/document domain specialist

Branch: `codex/25-reading`. Python via `.venv/bin/python`. Create ONE new module
`scripts/specialist_reading.py` + tests `tests/test_specialist_reading.py`. Do NOT edit other files.

## Why
When the activity is reading (a document/article/book on screen or paper), capture WHAT was read:
title, key entities/numbers, and a short gist — so "what was that article about / what dose did the
paper say" is answerable later. Generic OCR dumps text; this structures it.

## The module: `scripts/specialist_reading.py`

```python
import re

def extract(perception):
    """perception = {"objects":[str],"texts":[str],"caption":str}. From the OCR texts + caption:
      - title: the longest / most title-like text line (heuristic: a short line with title-case or
        all-caps, not a sentence) or the first non-trivial line.
      - numbers: list of salient '<number> <unit>' mentions (regex '\\d+(?:\\.\\d+)?\\s?(mg|g|kg|ml|l|%|mph|km|kg|usd|eur|\\$|€)' ),
      - entities: capitalized multi-word phrases (proper-noun-ish) up to ~8,
      - gist: first ~200 chars of concatenated body text.
    Return {"title": str|None, "numbers": [str], "entities": [str], "gist": str, "summary": str}.
    """

def answer(facts, question):
    """'what was it about / what did I read' -> title + gist; 'what dose / how much / what number'
    -> the relevant number(s); 'who/what was mentioned' -> entities. Return {"answer":str,"refused":bool}
    or None if not a reading question. Refuse honestly if the asked detail isn't present."""
```

## Acceptance tests (`tests/test_specialist_reading.py`)
1. texts ['Effects of Vitamin D','The study used 2000 IU daily','dose 50 mg'] ->
   numbers include '50 mg'; title mentions 'Vitamin D'.
2. answer(facts, 'what dose did it mention') -> mentions '50 mg', refused False.
3. answer(facts, 'what was the article about') -> mentions the title/gist, refused False.
4. answer(facts, 'what number') when no numbers -> honest refuse.
5. entities picks up a capitalized name like 'Robert Sauer' from texts.
6. answer(facts, 'how much soya') -> None (not a reading question).

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch. Report results.
