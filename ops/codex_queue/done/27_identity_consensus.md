# CODEX BRIEF 27 — cross-frame identity consensus (reliable reads)

Branch: `codex/27-identity`. Python via `.venv/bin/python`. Create ONE new module
`scripts/identity_consensus.py` + tests `tests/test_identity_consensus.py`. Do NOT edit other files.

## Why
The per-crop VLM reads the SAME object differently across frames ("soya","scallops","paper bag").
A reliable foundation needs to (a) pick the consensus identity when frames AGREE, and (b) HEDGE /
flag uncertainty when they don't — instead of letting one confident-sounding misread through. This is
the reliability gate under the binder.

## The module: `scripts/identity_consensus.py`

```python
import re

GENERIC = {"object","thing","item","jar","bottle","bag","container","box","can","cup","spread",
           "snack","stuff","food"}

def normalize(label: str) -> str:
    """lowercase, strip punctuation, collapse whitespace."""

def resolve(reads: list[str]) -> dict:
    """Given the labels an object was read as across frames, return the consensus identity.

    - Count normalized, NON-generic reads. The top label is the consensus.
    - agreement = top_count / total_nongeneric_reads (0..1); 0 if no non-generic reads.
    - confidence tier: "high" if agreement>=0.6 and top_count>=2; "medium" if top_count>=2 or
      agreement>=0.5; else "low".
    - If only generic reads -> label = most common generic, tier "low".
    Return {"label": str, "tier": "high|medium|low", "agreement": float, "alternatives": [(label,count)...]}.
    """

def is_reliable(consensus: dict) -> bool:
    """True if tier in ('high','medium') — safe to assert; low -> the brain should hedge/refuse."""
```

## Acceptance tests (`tests/test_identity_consensus.py`)
1. reads ['Nutella','nutella','Nutella jar','Hazelnut spread'] -> label 'nutella', tier high
   (nutella agrees across 3, generic 'hazelnut spread' down-weighted).
2. reads ['soya','scallops','paper bag','snack'] -> low agreement, tier 'low', is_reliable False.
3. reads ['Pringles','Pringles','Pringles can'] -> 'pringles', tier high.
4. reads ['jar','bottle','container'] (all generic) -> tier 'low'.
5. empty reads -> tier 'low', label '' or 'unknown', is_reliable False.
6. alternatives lists the runner-up counts sorted desc.

## Guardrails
- Pure, deterministic, no network/LLM. `pytest tests/ -q` green. Commit on branch. Report results.
