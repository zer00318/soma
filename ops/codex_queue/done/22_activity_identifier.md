# CODEX BRIEF 22 — activity characterizer (the helper-identifier / dispatcher)

Branch: `codex/22-activity`. Python via `.venv/bin/python`. Create ONE new module
`scripts/activity_identifier.py` + tests `tests/test_activity_identifier.py`. Do NOT edit other files.

## Why
The system must recognise WHAT the person is doing and dispatch the right DOMAIN specialists, instead
of running generic OCR on everything. e.g. lichess on screen -> chess specialist; soya + bowls on a
counter -> cooking specialist. This is the router above the helpers.

## The module: `scripts/activity_identifier.py`

```python
# Each activity: distinctive cue words (objects/text/scene) + the specialist(s) to spawn.
ACTIVITIES = {
    "chess":    {"cues": ["chess","lichess","chess.com","chessboard","pawn","knight","bishop","checkmate","opening"],
                 "specialists": ["chess"]},
    "cooking":  {"cues": ["bowl","pan","pot","knife","cutting board","ingredient","flour","soya","soy","spice",
                          "recipe","stove","measuring","utensil","jar","oil"],
                 "specialists": ["cooking"]},
    "reading":  {"cues": ["book","page","paragraph","document","article","pdf","chapter"],
                 "specialists": ["document"]},
    "coding":   {"cues": ["code","terminal","editor","vscode","function","import","def ","repository","github"],
                 "specialists": ["code"]},
    "shopping": {"cues": ["price","cart","checkout","store","aisle","€","$","product","shelf"],
                 "specialists": ["shopping"]},
}

def identify(perception, min_score=1):
    """Recognise the activity from a frame/moment's derived perception.

    perception = {
        "objects": [str, ...],   # detector/VLM object labels
        "texts":   [str, ...],   # OCR / read brand text
        "caption": str,          # scene caption
    }  (any key may be missing)

    Score each activity by how many distinct cue words appear (case-insensitive, word-ish match)
    across objects+texts+caption. Return:
      {
        "activity": <top activity or "generic">,
        "confidence": <0..1 = top_score / (top_score + runner_up + 1)>,
        "ranked": [(activity, score), ...] sorted desc (only score>0),
        "specialists": [ ... specialists to spawn for the top activity, [] if generic ],
        "cues_hit": [matched cue words],
      }
    If no activity scores >= min_score -> activity "generic", specialists [].
    """

def specialists_for(activity: str) -> list[str]:
    return ACTIVITIES.get(activity, {}).get("specialists", [])
```

## Acceptance tests (`tests/test_activity_identifier.py`)
1. perception with objects ["bowl","knife"], texts ["soya","flour"] -> activity "cooking",
   specialists ["cooking"], confidence>0.5.
2. caption "playing lichess, white to move" + texts ["chess.com"] -> "chess".
3. objects ["book"], caption "reading a long article about history" -> "reading".
4. texts ["def main()","import os"], caption "code editor terminal" -> "coding".
5. nothing matches (objects ["wall","floor"]) -> "generic", specialists [].
6. cooking cues AND one chess cue -> cooking wins (higher score); ranked lists both.

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch. Report results.
