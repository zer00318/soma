# CODEX BRIEF 24 — chess domain specialist (move list -> opening)

Branch: `codex/24-chess`. Python via `.venv/bin/python`. Create ONE new module
`scripts/specialist_chess.py` + tests `tests/test_specialist_chess.py`. Do NOT edit other files.

## Why
When the activity is chess (lichess/chess.com on screen), don't OCR pixels — understand the GAME.
The board UIs show a MOVE LIST in algebraic notation ("1. e4 d5 2. exd5 Qxd5 ..."). Read that move
sequence and identify the OPENING, so "what opening did I play?" -> "Scandinavian Defense".

## The module: `scripts/specialist_chess.py`

```python
import re

# First-moves -> opening name (prefix match on the SAN move list, longest prefix wins).
OPENINGS = [
    (["e4","d5"], "Scandinavian Defense"),
    (["e4","c5"], "Sicilian Defense"),
    (["e4","e5"], "Open Game / King's Pawn"),
    (["e4","e6"], "French Defense"),
    (["e4","c6"], "Caro-Kann Defense"),
    (["d4","d5"], "Queen's Pawn / Closed"),
    (["d4","Nf6"], "Indian Defense"),
    (["c4"], "English Opening"),
    (["Nf3"], "Reti Opening"),
    (["e4"], "King's Pawn Opening"),
    (["d4"], "Queen's Pawn Opening"),
]

def parse_moves(text):
    """Extract the SAN move sequence from a move-list string. Handle move numbers and dots:
    '1. e4 d5 2. exd5 Qxd5' -> ['e4','d5','exd5','Qxd5']. Strip annotations (!,?,+,#) for matching
    but you may keep the cleaned tokens. Return [] if none found."""

def identify_opening(moves):
    """Return the opening name for a move list (longest matching prefix in OPENINGS), or
    'Unknown opening' if no prefix matches / no moves."""

def extract(perception):
    """perception = {"objects":[str],"texts":[str],"caption":str}. Concatenate texts+caption,
    parse_moves, identify_opening. Return:
      {"moves":[...], "opening": str, "move_count": int,
       "result": <'win'/'loss'/'draw'/None from any '1-0','0-1','1/2-1/2' or 'won'/'lost'/'checkmate' cue>,
       "summary": str}.
    """

def answer(facts, question):
    """'what opening (did I play)' -> the opening; 'how many moves' -> move_count;
    'did I win / what was the result' -> result (or honest unknown). Return
    {"answer":str,"refused":bool} or None if not a chess question."""
```

## Acceptance tests (`tests/test_specialist_chess.py`)
1. parse_moves('1. e4 d5 2. exd5 Qxd5 3. Nc3') -> ['e4','d5','exd5','Qxd5','Nc3'].
2. identify_opening(['e4','d5']) -> 'Scandinavian Defense'; ['e4','c5'] -> 'Sicilian Defense';
   ['d4','Nf6'] -> 'Indian Defense'; [] -> 'Unknown opening'.
3. extract perception texts ['1. e4 d5 2. exd5 Qxd5'] -> opening 'Scandinavian Defense', move_count 4.
4. extract with '... 1-0' present -> result 'win'.
5. answer(facts, 'what opening did I play') -> mentions 'Scandinavian', refused False.
6. answer(facts, 'how much soya') -> None (not a chess question).

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch. Report results.
