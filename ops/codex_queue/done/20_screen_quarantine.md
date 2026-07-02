# CODEX BRIEF 20 — screen-content quarantine (the binder rule that completes coordinate counting)

Branch: `codex/20-screen-quarantine`. Python via `.venv/bin/python`. Create ONE new module
`scripts/screen_quarantine.py` + tests `tests/test_screen_quarantine.py`. Do NOT edit other files.

## Why (the founder's architecture)
On a real capture, the camera saw a laptop showing a chat that mentioned "Nutella/Pringles/Doritos".
The per-crop VLM read those WORDS off the screen and the binder created PHYSICAL nodes for them ->
"1 nutella" when there is no physical nutella. The founder's principle: on-screen content lives at
the SCREEN's location and must bind to the SCREEN node, not become phantom physical objects. So:
any detection whose box sits INSIDE a screen's box is screen-content — quarantine it.

## The module: `scripts/screen_quarantine.py`

```python
SCREEN_TYPES = {"laptop", "monitor", "tablet", "phone", "tv", "screen", "display"}

def mark_on_screen(instances):
    """Annotate each per-frame instance with on_screen / screen info, IN PLACE-safe (return a
    NEW list of dicts). instances = one frame's detections, each with normalized 'type' (or
    'det_label') and 'box' [x0,y0,x1,y1] (+ 'img_wh').

    1. Identify SCREEN instances: normalized type in SCREEN_TYPES.
    2. For every NON-screen instance, if its box is >=70% contained in some screen instance's box,
       mark it: inst['on_screen'] = True, inst['screen_type'] = <that screen's type>.
       Otherwise inst['on_screen'] = False.
    3. Screen instances themselves get on_screen=False (they ARE the physical object).
    Return the annotated list. Reuse a containment ratio (area of inst inside screen / area inst).
    """

def physical_only(instances):
    """Return only instances with on_screen falsy (drop screen-content reads). The world binder
    counts PHYSICAL objects from these; the on_screen reads can still be attached to the screen
    node's attributes elsewhere."""
```

## Honest rule
- Do NOT delete on_screen instances destructively — annotate; `physical_only` filters a view.
- A screen with no contained detections changes nothing.
- Be conservative: only quarantine when containment >= 0.70 (clearly inside the screen).

## Acceptance tests (`tests/test_screen_quarantine.py`)
1. A 'laptop' box [0,0,1000,700] (img 1000x1000) + a 'jar' box [100,100,300,300] (inside) ->
   the jar gets on_screen=True, screen_type='laptop'; the laptop on_screen=False.
2. A 'jar' box OUTSIDE the laptop (e.g. [800,800,950,950]) -> on_screen=False.
3. physical_only drops the on-screen jar, keeps the laptop and the outside jar.
4. No screen present -> nothing marked on_screen; physical_only returns all.
5. Partial overlap (40% inside) -> NOT quarantined (on_screen=False).
6. Two screens; a detection inside the second -> screen_type matches the containing screen.

## Guardrails
- Pure, deterministic, no I/O / network / LLM. `pytest tests/ -q` green. Commit on branch. Report results.
