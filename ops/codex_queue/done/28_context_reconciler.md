# CODEX BRIEF 28 — context reconciler (the "compounding brain" — priors between binder and brain)

Branch: `codex/28-reconciler`. Python via `.venv/bin/python`. Create ONE new module
`scripts/context_reconciler.py` + tests `tests/test_context_reconciler.py`. Do NOT edit other files.

## Why (founder's design)
A stop BETWEEN the binder and the reasoning brain. Helper reads conflict ("rocks","soya","paper bag")
for one object. Don't discard the whole thing as mixed signals — use the ACTIVITY/SCENE PRIOR: in a
KITCHEN, "soya" is plausible, "rocks" is not. Keep the plausible reading, drop the implausible, and
carry CALIBRATED uncertainty so the brain can answer honestly-but-helpfully later ("not sure it's
soya, but if it is, here's where and the amount"). This module owns the deterministic reconciliation;
the plausibility judgement is an INJECTED function (a local LLM at runtime, a stub in tests).

## The module: `scripts/context_reconciler.py`

```python
def reconcile_node(reads, activity, plausibility_fn):
    """Reconcile one object's conflicting identity reads using an activity prior.

    reads = [str] (the labels this object was read as across frames).
    activity = str (e.g. "cooking", "chess", or "generic").
    plausibility_fn(candidate:str, activity:str) -> float in 0..1 (how plausible this candidate is
        for this activity). Injected — runtime passes an LLM-backed fn; tests pass a stub dict-fn.

    Steps:
      - Normalize + count distinct candidate labels (drop empties/generics like 'object','thing').
      - Score each candidate = read_count_weight * plausibility_fn(candidate, activity).
        (read_count_weight = 1 + log-ish bump for repeats; keep it simple: count itself.)
      - DROP candidates whose plausibility < 0.2 (activity-implausible, e.g. 'rocks' in cooking).
      - chosen = highest combined score (or None if all dropped).
      - confidence = chosen_score / sum(all surviving scores) (0..1); reflects how dominant it is.
      - reliable = confidence >= 0.6 and chosen is not None.
    Return {"chosen": str|None, "confidence": float, "reliable": bool,
            "candidates": [(label, count, plausibility), ...] sorted desc by score,
            "dropped": [implausible labels]}.
    """

def reconcile(nodes, activity, plausibility_fn):
    """Apply reconcile_node to each node's 'texts'; attach node['reconciled'] = result and
    node['identity'] = chosen (or keep existing if None). Return the nodes (mutated copies ok)."""

def phrase_uncertainty(reconciled, detail):
    """Helper for honest-but-helpful answers. Given a reconciled identity and a detail string,
    return a phrasing:
      - reliable -> f"{detail}"
      - not reliable but has a chosen -> f"I'm not certain it was {chosen}, but if it was, {detail}"
      - no chosen -> None
    """
```

## Acceptance tests (`tests/test_context_reconciler.py`)
Use a stub plausibility_fn, e.g. for cooking: soya=0.9, scallops=0.4, "paper bag"=0.5, rocks=0.05.
1. reconcile_node(['rocks','soya','soya','paper bag'], 'cooking', stub) -> chosen 'soya',
   'rocks' in dropped, reliable depends on dominance (assert chosen=='soya', 'rocks' dropped).
2. reconcile_node(['rocks'], 'cooking', stub) -> chosen None (only implausible), reliable False.
3. reconcile_node(['soya','soya','soya'], 'cooking', stub) -> reliable True, confidence high.
4. phrase_uncertainty({'chosen':'soya','reliable':False}, '~250 ml') ->
   "I'm not certain it was soya, but if it was, ~250 ml".
5. phrase_uncertainty({'chosen':'soya','reliable':True}, '~250 ml') -> "~250 ml".
6. reconcile() attaches 'reconciled' + sets node['identity'] to the chosen.

## Guardrails
- Pure, deterministic (plausibility is injected). No network/LLM inside. `pytest tests/ -q` green.
  Commit on branch. Report results.
